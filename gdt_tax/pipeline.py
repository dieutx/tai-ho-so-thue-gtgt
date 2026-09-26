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
from .constants import METADATA_CSV, METADATA_JSON, SOURCE_ETAX_LEGACY
from .csrf import csrf_token
from .dates import format_date
from .errors import LegacyEtaxError, LoginError, SearchError
from .http import HttpClient
from .models import CaseRecord, PageResult, RunSummary, SearchPeriod
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
        #: Đoạn hiện tại có hồ sơ mà cổng trả lỗi tải (HTTP 500) hay không.
        self._period_had_download_error = False

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
        #: Đoạn đầu tiên gặp lỗi tải (HTTP 500) trên cổng — mốc mà từ đó dữ
        #: liệu cổng không còn đáng tin và phải chuyển sang trang legacy.
        self._first_failed_period: SearchPeriod | None = None
        #: True khi đã phát hiện lỗi tải: mọi đoạn sau đó chạy thẳng legacy.
        self._switched_to_legacy = False

        for period in self.settings.periods():
            summary.periods += 1
            portal = portals[period.source]
            use_legacy = (
                self._switched_to_legacy
                and period.end < self.settings.etax_cutoff
                and getattr(portal, "legacy", None) is not None
                and not self.settings.case_id
            )
            if use_legacy:
                self.logger.info("=== %s (trang cũ): %s ===", period.source, period.label)
                self._search_and_download(portal.legacy, period, records, succeeded)
                continue

            self.logger.info("=== %s: %s ===", period.source, period.label)
            if self._run_period(portal, period, records, succeeded):
                break

            # Một đoạn bất kỳ trước mốc mà cổng có hồ sơ nhưng không tải được
            # (HTTP 500 "Không tìm thấy hồ sơ tương ứng") thì dữ liệu cổng từ
            # đầu khoảng đến hết đoạn này không còn đáng tin: quét legacy từ
            # đầu khoảng đến hết đoạn để không sót tờ khai, và các đoạn cũ
            # hơn chạy thẳng legacy luôn không thử cổng nữa.
            if (
                self._first_failed_period is not None
                and period.end < self.settings.etax_cutoff
                and getattr(portal, "legacy", None) is not None
                and not self.settings.case_id
            ):
                self._switched_to_legacy = True
                self._run_legacy_fallback(portal, records, succeeded)

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
        self._period_had_download_error = False
        found_target = self._search_and_download(portal, period, records, succeeded)
        if found_target:
            return True
        # Đoạn có hồ sơ nhưng lỗi tải (HTTP 500): ghi nhận đoạn ĐẦU TIÊN gặp
        # lỗi. Đoạn 0 bản ghi thì không — cổng trả rỗng là bình thường với
        # khoảng không có hồ sơ.
        if self._period_had_download_error and self._first_failed_period is None:
            self._first_failed_period = period
            self.logger.warning(
                "Cổng có hồ sơ nhưng không tải được ở %s — sẽ quét trang Thuế điện tử "
                "cũ từ đầu khoảng đến hết đoạn này",
                period.label,
            )
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
        seen_ids: set[str] = set()

        while total_pages is None or page <= total_pages:
            result = self._search_page(portal, period, page)
            if result.total_pages is not None:
                total_pages = result.total_pages
            self.logger.info("TRANG %s: %s hồ sơ", page, len(result.records))
            page_ids = {found.ma_ho_so for found in result.records}
            new_ids = page_ids - seen_ids
            seen_ids.update(page_ids)

            for index, found in enumerate(result.records, start=1):
                if self.settings.case_id and found.ma_ho_so != self.settings.case_id:
                    continue
                record = records.setdefault(found.ma_ho_so, found)
                # Bản ghi legacy thay thế bản cổng (cùng mã): hồ sơ cổng bị 500
                # cần được tải lại qua portal legacy với đúng nguồn của nó.
                if found.nguon == SOURCE_ETAX_LEGACY and record.nguon != SOURCE_ETAX_LEGACY:
                    record.__dict__.update(found.__dict__)

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

            # Cổng không báo tổng số trang: dừng khi trang kế tiếp không còn hồ sơ
            # mới. Nếu không, trang sau lặp lại đúng bảng kết quả sẽ quay vô hạn.
            if total_pages is None and not new_ids:
                break
            page += 1
            if total_pages is None or page <= total_pages:
                self._pause(self.settings.pause_between_pages)
        return False

    def _run_legacy_fallback(
        self,
        portal,
        records: dict[str, CaseRecord],
        succeeded: set[str],
    ) -> None:
        """Quét trang Thuế điện tử cũ từ đầu khoảng đến hết đoạn lỗi.

        Khi cổng trả lỗi tải (HTTP 500) ở một đoạn bất kỳ trước mốc, các tờ
        khai cũ có thể bị mất khỏi cổng dù vẫn hiện trong kết quả tra cứu.
        Để không sót, mọi đoạn đã lập kế hoạch từ ``from_date`` đến hết đoạn lỗi
        được quét lại trên trang legacy, vẫn giữ nguyên kích thước đoạn (≤31 ngày)
        để trang cũ không từ chối khoảng quá dài; hồ sơ đã tải thành công từ cổng
        thì bỏ qua (dựa trên ``succeeded``), hồ sơ cổng trả 500 được thay bằng
        bản ghi legacy để tải lại.
        """
        failed_period = self._first_failed_period
        if failed_period is None:
            return
        for period in self.settings.periods():
            if period.start > failed_period.end:
                break
            legacy_period = SearchPeriod(
                start=period.start,
                end=min(period.end, failed_period.end),
                source=SOURCE_ETAX_LEGACY,
            )
            self.logger.info("Quét trang Thuế điện tử cũ cho %s", legacy_period.label)
            try:
                self._search_and_download(portal.legacy, legacy_period, records, succeeded)
            except LegacyEtaxError as error:
                self.logger.error("Trang legacy lỗi: %s — bỏ qua nguồn dự phòng", error)
                return

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
            self._period_had_download_error = True
            return False

        response = portal.download(record, detail_url, csrf)
        if response is None or response.status_code != 200:
            status = getattr(response, "status_code", "-")
            body = (getattr(response, "text", "") or "")[:300]
            self.logger.error("LỖI TẢI: %s HTTP=%s %s", record.ma_ho_so, status, body)
            self._period_had_download_error = True
            return False

        if self.store.save_from_response(record, response) is None:
            self._period_had_download_error = True
            return False
        succeeded.add(record.ma_ho_so)
        return True


__all__ = ["Pipeline"]
