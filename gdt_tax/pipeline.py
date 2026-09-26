"""Luồng chạy hoàn chỉnh, chia thành các giai đoạn rõ ràng.

::

    Giai đoạn 1  Đăng nhập và mở trang hồ sơ          gdt_tax.auth
    Giai đoạn 2  Lập kế hoạch đoạn tra cứu 31 ngày    gdt_tax.dates
    Giai đoạn 3  Tra cứu từng trang, đọc bảng kết quả gdt_tax.portals
    Giai đoạn 4  Tải ZIP từng hồ sơ, lưu + metadata  gdt_tax.storage
    Giai đoạn 5  Xuất danh sách hồ sơ cuối cùng       gdt_tax.storage

Cổng lưu danh sách hồ sơ của trang tra cứu gần nhất trong phiên, nên phải tải
ngay trên từng trang (giai đoạn 3 → 4) thay vì gom hết mã hồ sơ rồi mới tải;
nếu không sẽ gặp lỗi ``validateIdTkhai``.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from .auth import login, open_landing
from .constants import METADATA_CSV, METADATA_JSON
from .csrf import csrf_token
from .dates import format_date
from .errors import LegacyEtaxError, LoginError, SearchError
from .http import HttpClient
from .models import CaseRecord, PageResult, RunSummary
from .portals import build_portals
from .storage import ZipStore, write_metadata

LOGGER_NAME = "gdt_tax.pipeline"
SEARCH_RETRY_PAUSE = 4.0


class Pipeline:
    """Ghép các giai đoạn và giữ trạng thái của một lần chạy."""

    def __init__(
        self,
        settings,
        http: HttpClient,
        captcha,
        *,
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

    # --- Giai đoạn 1 + điều phối ---
    def run(self) -> RunSummary:
        summary = RunSummary(dry_run=self.settings.dry_run)
        self.logger.info(
            "Bắt đầu: %s → %s (đổi nguồn dữ liệu tại %s)",
            format_date(self.settings.from_date),
            format_date(self.settings.to_date),
            format_date(self.settings.etax_cutoff),
        )

        if not login(self.http, self.captcha, self.settings, self.logger):
            raise LoginError("ĐĂNG NHẬP THẤT BẠI")

        landing = open_landing(self.http, self.logger, profile=self.settings.header_profile)
        portals = self.portal_factory(
            self.http, self.captcha, self.settings, csrf_token(landing), self.logger
        )

        records: dict[str, CaseRecord] = {}
        succeeded: set[str] = set()
        #: (đoạn, đúng là không tải được hồ sơ nào) của đoạn vừa chạy xong.
        self._period_without_download = (None, False)

        for period in self.settings.periods():
            summary.periods += 1
            self.logger.info("=== %s: %s ===", period.source, period.label)
            portal = portals[period.source]
            if self._run_period(portal, period, records, succeeded):
                break
            # Nguồn dự phòng trang Thuế điện tử cũ: đoạn ngày trước mốc mà cổng
            # không tải được hồ sơ nào (kể cả khi cổng vẫn "hiện" hồ sơ cũ) thì
            # hỏi thêm trang legacy, nơi một số tờ khai cũ chỉ còn tồn tại.
            if (
                not self.settings.case_id
                and period.end < self.settings.etax_cutoff
                and getattr(portal, "legacy", None) is not None
            ):
                self._run_legacy_fallback(portal, period, records, succeeded)

        if write_metadata(self.settings.download_dir, records):
            self.logger.info("Metadata: %s và %s", METADATA_CSV, METADATA_JSON)

        summary.downloaded = len(succeeded)
        summary.expected = 1 if self.settings.case_id else len(records)
        return summary

    # --- Giai đoạn 3 + 4 ---
    def _run_period(
        self,
        portal,
        period,
        records: dict[str, CaseRecord],
        succeeded: set[str],
    ) -> bool:
        """Xử lý mọi trang của một đoạn; trả ``True`` khi đã tìm thấy hồ sơ đích."""
        before = len(succeeded)
        found_target = self._search_and_download(portal, period, records, succeeded)
        if found_target:
            return True
        # Ghi nhớ đoạn có portal gốc nhưng không tải được hồ sơ nào để fallback.
        self._period_without_download = (period, before == len(succeeded))
        return False

    def _search_and_download(
        self,
        portal,
        period,
        records: dict[str, CaseRecord],
        succeeded: set[str],
    ) -> bool:
        """Duyệt hết trang của một đoạn trên một portal; trả ``True`` khi tìm thấy hồ sơ đích."""
        page = 1
        total_pages: int | None = None

        while total_pages is None or page <= total_pages:
            result = self._search_page(portal, period, page)
            if result.total_pages is not None:
                total_pages = result.total_pages
            self.logger.info("TRANG %s: %s hồ sơ", page, len(result.records))

            for index, found in enumerate(result.records, start=1):
                record = records.setdefault(found.ma_ho_so, found)
                if self.settings.case_id and record.ma_ho_so != self.settings.case_id:
                    continue

                self.logger.info(
                    "TẢI trang=%s mục=%s/%s: %s",
                    page,
                    index,
                    len(result.records),
                    record.ma_ho_so,
                )
                self._download(portal, record, succeeded)
                write_metadata(self.settings.download_dir, records)

                if self.settings.case_id and record.ma_ho_so == self.settings.case_id:
                    return True
                self._pause(self.settings.pause_between_records)

            if total_pages is None and not result.records:
                break
            page += 1
            if total_pages is None or page <= total_pages:
                self._pause(self.settings.pause_between_pages)
        return False

    def _run_legacy_fallback(
        self,
        portal,
        period,
        records: dict[str, CaseRecord],
        succeeded: set[str],
    ) -> None:
        """Hỏi trang Thuế điện tử cũ khi cổng không tải được hồ sơ nào của đoạn.

        Cổng có lúc còn hiển thị hồ sơ cũ trong kết quả tra cứu nhưng máy chủ
        tải ZIP trả "Không tìm thấy hồ sơ tương ứng" — những tờ khai này chỉ còn
        lấy được trên trang legacy. Kết quả legacy được ghi nhận như hồ sơ bình
        thường (``nguon = ETAX_LEGACY``) và tải qua ``portal.legacy``.
        """
        period, without_download = self._period_without_download
        if not without_download:
            return
        self.logger.info(
            "Cổng không tải được hồ sơ nào cho %s — hỏi trang Thuế điện tử cũ", period.label
        )
        try:
            self._search_and_download(portal.legacy, period, records, succeeded)
        except LegacyEtaxError as error:
            self.logger.error("Trang legacy lỗi: %s — bỏ qua nguồn dự phòng", error)

    def _pause(self, seconds: float) -> None:
        """Nghỉ giữa hai request, thêm chút ngẫu nhiên cho nhịp tự nhiên hơn.

        Jitter **chỉ cộng thêm** thời gian, không bao giờ rút ngắn, nên không làm
        tăng tần suất request — vẫn giữ đúng phép lịch sự với cổng (ngoài ra
        ``HttpClient`` còn tôn trọng ``Retry-After``).
        """
        jitter = self.settings.pause_jitter
        delay = seconds * (1 + random.uniform(0, jitter)) if jitter > 0 and seconds > 0 else seconds
        if delay != seconds:
            self.logger.debug("Nghỉ %.1fs (đã cộng jitter)", delay)
        self.sleep(delay)

    def _search_page(self, portal, period, page: int) -> PageResult:
        """Tra cứu một trang, tự thử lại khi cổng trả về rỗng (thường do CAPTCHA sai)."""
        for attempt in range(1, self.settings.search_attempts + 1):
            result = portal.search(period, page)
            self.logger.info(
                "SEARCH %s %s page=%s try=%s: HTTP=%s, records=%s, pages=%s",
                portal.source,
                period.label,
                page,
                attempt,
                result.http_status,
                len(result.records),
                result.total_pages,
            )
            if result.records or result.total_pages is not None:
                return result
            self._pause(SEARCH_RETRY_PAUSE)
        raise SearchError(
            f"Không tìm được trang {page} sau {self.settings.search_attempts} lần thử"
        )

    # --- Giai đoạn 4 ---
    def _download(self, portal, record: CaseRecord, succeeded: set[str]) -> bool:
        if self.store.find_existing(record):
            succeeded.add(record.ma_ho_so)
            return True

        if self.settings.dry_run:
            self.logger.info("Dry-run: bỏ qua tải %s", record.ma_ho_so)
            return False

        detail_url, csrf = portal.fetch_detail_csrf(record)
        # Trang Thuế điện tử cũ không dùng CSRF token khi tải (csrf_optional=True);
        # các nguồn DVC/ETAX trên cổng đều phải có token mới tải được.
        if not csrf and not getattr(portal, "csrf_optional", False):
            self.logger.error("LỖI TẢI: không lấy được CSRF token cho %s", record.ma_ho_so)
            return False

        response = portal.download(record, detail_url, csrf)
        if response is None or response.status_code != 200:
            status = getattr(response, "status_code", "-")
            body = (getattr(response, "text", "") or "")[:300]
            self.logger.error("LỖI TẢI: %s HTTP=%s %s", record.ma_ho_so, status, body)
            return False

        if self.store.save_from_response(record, response) is None:
            return False
        succeeded.add(record.ma_ho_so)
        return True


__all__ = ["Pipeline"]
