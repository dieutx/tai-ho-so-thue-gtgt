"""Lập kế hoạch, đăng nhập theo nguồn và tải ngay trong từng trang kết quả."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from .auth import login, open_landing
from .catalog import CatalogCheckpoint, flush_on_error
from .classification import classify_record
from .constants import METADATA_CSV, METADATA_JSON, METADATA_XLSX, SOURCE_ETAX_LEGACY
from .csrf import csrf_token
from .dates import format_date
from .errors import LoginError, NetworkError, SchemaChangedError, SearchError
from .http import HttpClient
from .identity import account_fingerprint, scope_targets
from .models import CaseRecord, PageResult, RunSummary
from .ownership import prepare_output
from .portals import build_portals
from .run_hooks import RunBudget, RunHooks
from .storage import ZipStore, write_metadata

LOGGER_NAME = "gdt_tax.pipeline"
SEARCH_RETRY_PAUSE = 4.0


class Pipeline:
    def __init__(
        self, settings, http: HttpClient, captcha, *,
        store: ZipStore | None = None,
        portal_factory: Callable[..., dict] = build_portals,
        logger: logging.Logger | None = None,
        sleep: Callable[[float], None] = time.sleep,
        hooks: RunHooks | None = None,
        persist_metadata: bool = True,
        target_ids: set[str] | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.captcha = captcha
        self.store = store or ZipStore(settings.download_dir)
        self.portal_factory = portal_factory
        self.logger = logger or logging.getLogger(LOGGER_NAME)
        self.sleep = sleep
        self.hooks: RunHooks = hooks or getattr(http, "hooks", None) or RunHooks()
        if self.hooks.budget is None:
            self.hooks.budget = RunBudget()
        self.persist_metadata = persist_metadata
        self.checkpoint = CatalogCheckpoint(write_metadata, settings.download_dir,
                                            enabled=persist_metadata and not settings.dry_run)
        self.target_ids = target_ids
        self.account_key = account_fingerprint(settings.username)
        self.case_targets: set[str] | None = None
        self.record_errors: dict[str, str] = {}
        self.active_record_id = ""
        self.records: dict = {}
        self.downloaded_ids: set[str] = set()
        self.failed_ids: set[str] = set()
        self.reused_ids: set[str] = set()

    def _persist(self, records, **kwargs):
        return self.checkpoint.persist(records, **kwargs)

    def _attempt_download(self, portal, record, succeeded):
        try:
            return self._download(portal, record, succeeded)
        except NetworkError as error:
            if self.target_ids is None:
                raise
            self.record_errors[record.record_key] = str(error)
            self.logger.error("Không tải được hồ sơ %s: %s", record.ma_ho_so, error)
            return False

    @flush_on_error
    def run(self) -> RunSummary:
        self.record_errors = {}
        self.active_record_id = ""
        self.case_targets = None
        self.records = {}
        self.downloaded_ids = set()
        self.failed_ids = set()
        self.reused_ids = set()
        summary = RunSummary(dry_run=self.settings.dry_run)
        self.logger.info(
            "Bắt đầu: %s → %s (cutoff %s; DVC %s)",
            format_date(self.settings.from_date), format_date(self.settings.to_date),
            format_date(self.settings.etax_cutoff),
            "bật" if self.settings.dvc_enabled else "tạm tắt",
        )
        active = []
        for period in self.settings.periods():
            if self.settings.source_enabled(period.source):
                active.append(period)
            else:
                summary.skipped_periods += 1
                self.logger.warning(
                    "BỎ QUA %s: %s — DVC đang tạm tắt; kết quả chưa đầy đủ",
                    period.source, period.label,
                )

        sources = {period.source for period in active}
        if self.target_ids is not None:
            self.target_ids = scope_targets(self.target_ids, account_key=self.account_key,
                                           sources=sources, document_kind="DECLARATION")
        if self.settings.case_id and sources:
            self.case_targets = scope_targets([self.settings.case_id], account_key=self.account_key,
                                             sources=sources, document_kind="DECLARATION")
        if active:
            prepare_output(self.settings)
        # Legacy có phiên DSE riêng. Không phụ thuộc đăng nhập hay CSRF của DVC.
        csrf = ""
        if any(period.source != SOURCE_ETAX_LEGACY for period in active):
            if not login(self.http, self.captcha, self.settings, self.logger):
                raise LoginError("ĐĂNG NHẬP THẤT BẠI")
            landing = open_landing(self.http, self.logger, profile=self.settings.header_profile)
            csrf = csrf_token(landing)
        portals = self.portal_factory(self.http, self.captcha, self.settings, csrf, self.logger)

        records: dict[str, CaseRecord] = self.records
        succeeded: set[str] = self.downloaded_ids
        for period in active:
            self.hooks.check()
            summary.periods += 1
            self.logger.info("=== %s: %s ===", period.source, period.label)
            if self._search_and_download(portals[period.source], period, records, succeeded):
                break

        if self._persist(records, materialize=True):
            self.logger.info(
                "Metadata: %s, %s và %s; danh mục nhóm: phan_loai_ho_so.json",
                METADATA_CSV, METADATA_JSON, METADATA_XLSX,
            )
        summary.downloaded = len(succeeded)
        summary.discovered = len(records)
        summary.expected = len(self.target_ids) if self.target_ids is not None else 1 if self.settings.case_id else len(records)
        return summary

    def _search_and_download(self, portal, period, records, succeeded) -> bool:
        page = 1
        total_pages: int | None = None
        seen_ids: set[str] = set()
        while total_pages is None or page <= total_pages:
            self.hooks.check()
            result = self._search_page(portal, period, page)
            known_total = total_pages is not None
            if result.total_pages is not None:
                total_pages = result.total_pages
            page_ids = {found.ma_ho_so for found in result.records}
            new_ids = page_ids - seen_ids
            self.logger.info("TRANG %s: %s hồ sơ", page, len(result.records))
            if page > 1 and not new_ids:
                if known_total or result.records:
                    raise SearchError(
                        f"{portal.source} trang {page}/{total_pages} rỗng hoặc lặp lại; "
                        "không thể xác nhận đã tra cứu đủ"
                    )
                break
            if not result.records and total_pages is not None and total_pages > 1:
                raise SearchError(f"{portal.source} trang {page}/{total_pages} không có hồ sơ")
            seen_ids.update(page_ids)
            for index, found in enumerate(result.records, start=1):
                self.hooks.check()
                if found.nguon != period.source:
                    raise SchemaChangedError("RECORD_SOURCE_OUTSIDE_PLAN")
                found.account_key = self.account_key
                if self.case_targets is not None and found.record_key not in self.case_targets:
                    continue
                record = records.setdefault(found.record_key, classify_record(found))
                self.logger.info("TẢI trang=%s mục=%s/%s: %s", page, index, len(result.records), record.ma_ho_so)
                self.active_record_id = record.record_key
                targeted = self.target_ids is None or record.record_key in self.target_ids
                success = self._attempt_download(portal, record, succeeded) if targeted else False
                if not self.settings.dry_run and targeted:
                    if record.record_key in succeeded:
                        self.failed_ids.discard(record.record_key)
                    else:
                        self.failed_ids.add(record.record_key)
                self._persist(records)
                self.hooks.emit(record=record.to_dict(), discovered=len(records), downloaded=len(succeeded), errors=len(self.failed_ids), file_state="Đã có hợp lệ" if record.record_key in self.reused_ids else "Chỉ tra cứu" if self.settings.dry_run else "Đã tải" if record.record_key in succeeded else "Lỗi tải" if targeted else "Chưa tải")
                if self.settings.case_id and (success or self.settings.dry_run):
                    if result.diagnostics is None or result.diagnostics.complete:
                        return True
                if self.target_ids and self.target_ids.issubset(succeeded):
                    if result.diagnostics is None or result.diagnostics.complete:
                        return True
                self._pause(self.settings.pause_between_records)
            self._persist(records, force=True)
            if result.diagnostics is not None and not result.diagnostics.complete:
                raise SchemaChangedError("SCHEMA_CHANGED: " + "; ".join(result.diagnostics.reasons))
            if total_pages is None and not new_ids:
                break
            page += 1
            if total_pages is None or page <= total_pages:
                self._pause(self.settings.pause_between_pages)
        return False

    def _pause(self, seconds: float) -> None:
        jitter = self.settings.pause_jitter
        delay = seconds * (1 + random.uniform(0, jitter)) if jitter > 0 and seconds > 0 else seconds
        self.hooks.pause(delay, self.sleep)

    def _search_page(self, portal, period, page: int) -> PageResult:
        if self.hooks.budget is not None:
            self.hooks.budget.page()
        for attempt in range(1, self.settings.search_attempts + 1):
            self.hooks.check()
            result = portal.search(period, page)
            if result.diagnostics is not None and not result.diagnostics.complete and result.diagnostics.status != "CAPTCHA_INVALID":
                if result.records:
                    return result
                raise SchemaChangedError("SCHEMA_CHANGED: " + "; ".join(result.diagnostics.reasons))
            self.logger.info(
                "SEARCH %s %s page=%s try=%s: HTTP=%s, records=%s, pages=%s",
                portal.source, period.label, page, attempt, result.http_status,
                len(result.records), result.total_pages,
            )
            if result.http_status == 200 and (
                result.records or (result.diagnostics is not None and result.diagnostics.status == "EMPTY_CONFIRMED")
            ):
                return result
            if attempt < self.settings.search_attempts:
                self._pause(SEARCH_RETRY_PAUSE)
        raise SearchError(f"Không đọc được trang {page} sau {self.settings.search_attempts} lần thử")

    def _download(self, portal, record: CaseRecord, succeeded: set[str]) -> bool:
        # Dry-run không được dò/đổi tên file đã có hoặc tính chúng là vừa tải.
        if self.settings.dry_run:
            self.logger.info("Dry-run: bỏ qua tải %s", record.ma_ho_so)
            return False
        if record.record_key in succeeded:
            return True
        if self.store.find_existing(record):
            self.reused_ids.add(record.record_key)
            succeeded.add(record.record_key)
            return True
        detail_url, csrf = portal.fetch_detail_csrf(record)
        if not csrf and not getattr(portal, "csrf_optional", False):
            self.record_errors[record.record_key] = "Cổng không trả mã xác thực CSRF cho tệp. Kiểm tra phiên đăng nhập rồi thử lại."
            self.logger.error("LỖI TẢI: không lấy được CSRF token cho %s", record.ma_ho_so)
            return False
        response = portal.download(record, detail_url, csrf)
        if response is None or response.status_code != 200:
            self.record_errors[record.record_key] = f"Cổng trả HTTP {getattr(response, 'status_code', 'không có phản hồi')} khi tải tệp. Kiểm tra kết nối/phiên rồi thử lại."
            self.logger.error("LỖI TẢI: %s HTTP=%s", record.ma_ho_so, getattr(response, "status_code", "-"))
            return False
        if self.store.save_from_response(record, response) is None:
            self.record_errors[record.record_key] = "Dữ liệu trả về không phải ZIP hoàn chỉnh/hợp lệ. Tệp chưa được lưu; có thể phiên đã hết hạn."
            return False
        succeeded.add(record.record_key)
        return True


__all__ = ["Pipeline"]
