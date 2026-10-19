"""Lập kế hoạch, đăng nhập theo nguồn và tải ngay trong từng trang kết quả."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from .auth import login, open_landing
from .classification import classify_record
from .constants import METADATA_CSV, METADATA_JSON, METADATA_XLSX, SOURCE_ETAX_LEGACY
from .csrf import csrf_token
from .dates import format_date
from .errors import LoginError, NetworkError, SearchError
from .http import HttpClient
from .models import CaseRecord, PageResult, RunSummary
from .portals import build_portals
from .run_hooks import RunHooks
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
        self.hooks = hooks or RunHooks()
        self.persist_metadata = persist_metadata
        self.target_ids = target_ids
        self.record_errors: dict[str, str] = {}
        self.active_record_id = ""
        self.records: dict = {}
        self.downloaded_ids: set[str] = set()
        self.failed_ids: set[str] = set()
        self.reused_ids: set[str] = set()

    def _persist(self, records):
        return write_metadata(self.settings.download_dir, records) if self.persist_metadata else None

    def _attempt_download(self, portal, record, succeeded):
        try:
            return self._download(portal, record, succeeded)
        except NetworkError as error:
            if self.target_ids is None:
                raise
            self.record_errors[record.ma_ho_so] = str(error)
            self.logger.error("Không tải được hồ sơ %s: %s", record.ma_ho_so, error)
            return False

    def run(self) -> RunSummary:
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

        if self._persist(records):
            self.logger.info(
                "Metadata: %s, %s và %s; danh mục nhóm: phan_loai_ho_so.json",
                METADATA_CSV, METADATA_JSON, METADATA_XLSX,
            )
        summary.downloaded = len(succeeded)
        summary.discovered = len(records)
        summary.expected = 1 if self.settings.case_id else len(records)
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
                if self.settings.case_id and found.ma_ho_so != self.settings.case_id:
                    continue
                record = records.setdefault(found.ma_ho_so, classify_record(found))
                self.logger.info("TẢI trang=%s mục=%s/%s: %s", page, index, len(result.records), record.ma_ho_so)
                self.active_record_id = record.ma_ho_so
                targeted = self.target_ids is None or record.ma_ho_so in self.target_ids
                success = self._attempt_download(portal, record, succeeded) if targeted else False
                if not self.settings.dry_run and targeted:
                    if record.ma_ho_so in succeeded:
                        self.failed_ids.discard(record.ma_ho_so)
                    else:
                        self.failed_ids.add(record.ma_ho_so)
                self._persist(records)
                self.hooks.emit(record=record.to_dict(), discovered=len(records), downloaded=len(succeeded), errors=len(self.failed_ids), file_state="Đã có hợp lệ" if record.ma_ho_so in self.reused_ids else "Chỉ tra cứu" if self.settings.dry_run else "Đã tải" if record.ma_ho_so in succeeded else "Lỗi tải" if targeted else "Chưa tải")
                if self.settings.case_id and (success or self.settings.dry_run):
                    return True
                if self.target_ids and self.target_ids.issubset(succeeded):
                    return True
                self._pause(self.settings.pause_between_records)
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
        for attempt in range(1, self.settings.search_attempts + 1):
            self.hooks.check()
            result = portal.search(period, page)
            self.logger.info(
                "SEARCH %s %s page=%s try=%s: HTTP=%s, records=%s, pages=%s",
                portal.source, period.label, page, attempt, result.http_status,
                len(result.records), result.total_pages,
            )
            if result.http_status == 200 and (
                result.records or (result.total_pages is not None and result.total_pages >= 0)
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
        if record.ma_ho_so in succeeded:
            return True
        if self.store.find_existing(record):
            self.reused_ids.add(record.ma_ho_so)
            succeeded.add(record.ma_ho_so)
            return True
        detail_url, csrf = portal.fetch_detail_csrf(record)
        if not csrf and not getattr(portal, "csrf_optional", False):
            self.record_errors[record.ma_ho_so] = "Cổng không trả mã xác thực CSRF cho tệp. Kiểm tra phiên đăng nhập rồi thử lại."
            self.logger.error("LỖI TẢI: không lấy được CSRF token cho %s", record.ma_ho_so)
            return False
        response = portal.download(record, detail_url, csrf)
        if response is None or response.status_code != 200:
            self.record_errors[record.ma_ho_so] = f"Cổng trả HTTP {getattr(response, 'status_code', 'không có phản hồi')} khi tải tệp. Kiểm tra kết nối/phiên rồi thử lại."
            self.logger.error("LỖI TẢI: %s HTTP=%s", record.ma_ho_so, getattr(response, "status_code", "-"))
            return False
        if self.store.save_from_response(record, response) is None:
            self.record_errors[record.ma_ho_so] = "Dữ liệu trả về không phải ZIP hoàn chỉnh/hợp lệ. Tệp chưa được lưu; có thể phiên đã hết hạn."
            return False
        succeeded.add(record.ma_ho_so)
        return True


__all__ = ["Pipeline"]
