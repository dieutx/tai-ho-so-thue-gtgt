"""Lập kế hoạch, đăng nhập theo nguồn và tải ngay trong từng trang kết quả."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from .auth import login, open_landing
from .classification import classify_record
from .constants import (
    ACCOUNT_PERSONAL,
    METADATA_CSV,
    METADATA_JSON,
    METADATA_XLSX,
    SOURCE_ETAX_LEGACY,
)
from .csrf import csrf_token
from .dates import format_date
from .errors import LoginError, SearchError, StorageError
from .http import HttpClient
from .models import CaseRecord, PageResult, RunSummary
from .portals import build_portals
from .storage import ZipStore, write_metadata
from .taxpayer import Taxpayer, parse_taxpayer, save_taxpayer

LOGGER_NAME = "gdt_tax.pipeline"
SEARCH_RETRY_PAUSE = 4.0


class Pipeline:
    def __init__(
        self, settings, http: HttpClient, captcha, *,
        store: ZipStore | None = None,
        portal_factory: Callable[..., dict] = build_portals,
        logger: logging.Logger | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.http = http
        self.captcha = captcha
        self.store = store or ZipStore(settings.download_dir)
        self.portal_factory = portal_factory
        self.logger = logger or logging.getLogger(LOGGER_NAME)
        self.sleep = sleep
        self.taxpayer: Taxpayer | None = None

    def run(self) -> RunSummary:
        summary = RunSummary(dry_run=self.settings.dry_run)
        self.logger.info(
            "Bắt đầu: %s → %s (tài khoản %s; cutoff %s; DVC %s)",
            format_date(self.settings.from_date), format_date(self.settings.to_date),
            self.settings.account_type,
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
            doi_tuong = "CN" if self.settings.account_type == ACCOUNT_PERSONAL else "DN"
            if not login(
                self.http, self.captcha, self.settings, self.logger, doi_tuong=doi_tuong
            ):
                raise LoginError("ĐĂNG NHẬP THẤT BẠI")
            landing = open_landing(self.http, self.logger, profile=self.settings.header_profile)
            self._remember_taxpayer(landing)
            csrf = csrf_token(landing)
        portals = self.portal_factory(self.http, self.captcha, self.settings, csrf, self.logger)

        records: dict[str, CaseRecord] = {}
        succeeded: set[str] = set()
        for period in active:
            summary.periods += 1
            self.logger.info("=== %s: %s ===", period.source, period.label)
            if self._search_and_download(portals[period.source], period, records, succeeded):
                break

        if write_metadata(self.settings.download_dir, records):
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
                if self.settings.case_id and found.ma_ho_so != self.settings.case_id:
                    continue
                record = records.setdefault(found.ma_ho_so, classify_record(found))
                self._attach_taxpayer(record)
                self.logger.info("TẢI trang=%s mục=%s/%s: %s", page, index, len(result.records), record.ma_ho_so)
                success = self._download(portal, record, succeeded)
                write_metadata(self.settings.download_dir, records)
                if self.settings.case_id and (success or self.settings.dry_run):
                    return True
                self._pause(self.settings.pause_between_records)
            if total_pages is None and not new_ids:
                break
            page += 1
            if total_pages is None or page <= total_pages:
                self._pause(self.settings.pause_between_pages)
        return False

    def _remember_taxpayer(self, landing: str) -> None:
        """Đọc tên người nộp thuế từ trang hồ sơ và lưu theo mã số thuế."""
        taxpayer = parse_taxpayer(landing, self.settings.username)
        if taxpayer is None:
            self.logger.debug("Trang hồ sơ không có đủ tên và MST để lưu")
            return
        self.taxpayer = taxpayer
        self.logger.info(
            "NGƯỜI NỘP THUẾ: %s (MST %s)",
            taxpayer.ten_nguoi_nop_thue, taxpayer.mst,
        )
        try:
            path = save_taxpayer(self.settings.download_dir, taxpayer)
        except StorageError as error:
            self.logger.warning("%s", error)
        else:
            self.logger.info("Đã lưu tên người nộp thuế vào %s", path.name)

    def _attach_taxpayer(self, record: CaseRecord) -> None:
        """Gắn MST/tên đã đọc sau đăng nhập vào từng hồ sơ."""
        if self.taxpayer is None:
            return
        record.mst = record.mst or self.taxpayer.mst
        record.ten_nguoi_nop_thue = (
            record.ten_nguoi_nop_thue or self.taxpayer.ten_nguoi_nop_thue
        )

    def _pause(self, seconds: float) -> None:
        jitter = self.settings.pause_jitter
        delay = seconds * (1 + random.uniform(0, jitter)) if jitter > 0 and seconds > 0 else seconds
        self.sleep(delay)

    def _search_page(self, portal, period, page: int) -> PageResult:
        for attempt in range(1, self.settings.search_attempts + 1):
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
            succeeded.add(record.ma_ho_so)
            return True
        detail_url, csrf = portal.fetch_detail_csrf(record)
        if not csrf and not getattr(portal, "csrf_optional", False):
            self.logger.error("LỖI TẢI: không lấy được CSRF token cho %s", record.ma_ho_so)
            return False
        response = portal.download(record, detail_url, csrf)
        if response is None or response.status_code != 200:
            self.logger.error("LỖI TẢI: %s HTTP=%s", record.ma_ho_so, getattr(response, "status_code", "-"))
            return False
        if self.store.save_from_response(record, response) is None:
            return False
        succeeded.add(record.ma_ho_so)
        return True


__all__ = ["Pipeline"]
