"""Luồng tra cứu — tải PDF thông báo của cơ quan thuế.

Giống :class:`gdt_tax.gnt.pipeline.GntPipeline`: chia đoạn ngày, tra cứu và tải
ngay trên từng trang vì cổng chỉ giữ danh sách của trang gần nhất trong phiên.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable

from ..errors import SearchError
from ..http import HttpClient
from .models import TbPageResult, TbSummary, ThongBao, tb_periods
from .portal import TbPortal
from .storage import TbStore, write_tb_metadata

LOGGER_NAME = "gdt_tax.tb.pipeline"
SEARCH_RETRY_PAUSE = 4.0


class TbPipeline:
    """Tra cứu và tải thông báo của cơ quan thuế theo từng đoạn ngày."""

    def __init__(
        self,
        settings,
        http: HttpClient,
        captcha,
        *,
        store: TbStore | None = None,
        portal_factory: Callable[[], TbPortal] | None = None,
        logger: logging.Logger | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.http = http
        self.captcha = captcha
        self.store = store or TbStore(settings.download_dir)
        self.portal_factory = portal_factory
        self.logger = logger or logging.getLogger(LOGGER_NAME)
        self.sleep = sleep

    def run(self) -> TbSummary:
        summary = TbSummary(dry_run=self.settings.dry_run)
        periods = tb_periods(
            self.settings.from_date, self.settings.to_date, self.settings.max_days_per_search
        )
        self.logger.info(
            "Bắt đầu tra cứu thông báo: %s → %s (%s đoạn)",
            self.settings.from_date.strftime("%d/%m/%Y"),
            self.settings.to_date.strftime("%d/%m/%Y"),
            len(periods),
        )
        portal = self.portal_factory() if self.portal_factory else TbPortal(
            self.http, self.captcha, self.settings, self.logger
        )

        records: dict[str, ThongBao] = {}
        downloaded: set[str] = set()
        for period in periods:
            summary.periods += 1
            self.logger.info("=== Thông báo: %s ===", period.label)
            self._search_period(portal, period, records, downloaded)
            write_tb_metadata(self.settings.download_dir, records)

        if write_tb_metadata(self.settings.download_dir, records):
            self.logger.info("Thông báo: đã ghi danh sách (CSV/JSON/Excel)")
        summary.discovered = len(records)
        summary.downloaded = len(downloaded)
        return summary

    def _search_period(
        self,
        portal: TbPortal,
        period,
        records: dict[str, ThongBao],
        downloaded: set[str],
    ) -> None:
        page = 1
        total_pages: int | None = None
        seen_ids: set[str] = set()
        while total_pages is None or page <= total_pages:
            result = self._search_page(portal, period, page)
            known_total = total_pages is not None
            if result.total_pages is not None:
                total_pages = result.total_pages
            page_ids = {found.message_id for found in result.records}
            new_ids = page_ids - seen_ids
            self.logger.info("TRANG %s: %s thông báo", page, len(result.records))
            if page > 1 and not new_ids:
                if known_total or result.records:
                    raise SearchError(
                        f"Thông báo trang {page}/{total_pages} rỗng hoặc lặp lại; "
                        "không thể xác nhận đã tra cứu đủ"
                    )
                break
            if not result.records and total_pages is not None and total_pages > 1:
                raise SearchError(f"Trang {page}/{total_pages} thông báo trống")
            seen_ids.update(page_ids)
            for index, found in enumerate(result.records, start=1):
                records.setdefault(found.message_id, found)
                self.logger.info(
                    "TẢI trang=%s mục=%s/%s: %s",
                    page, index, len(result.records), found.so_thong_bao or found.message_id,
                )
                self._download(portal, found, downloaded)
                write_tb_metadata(self.settings.download_dir, records)
                self._pause(self.settings.pause_between_records)
            if total_pages is None and not new_ids:
                break
            page += 1
            if total_pages is None or page <= total_pages:
                self._pause(self.settings.pause_between_pages)

    def _pause(self, seconds: float) -> None:
        jitter = self.settings.pause_jitter
        delay = seconds * (1 + random.uniform(0, jitter)) if jitter > 0 and seconds > 0 else seconds
        self.sleep(delay)

    def _search_page(self, portal: TbPortal, period, page: int) -> TbPageResult:
        for attempt in range(1, self.settings.search_attempts + 1):
            result = portal.search_tb(period, page)
            self.logger.info(
                "SEARCH TB %s page=%s try=%s: HTTP=%s, records=%s, pages=%s",
                period.label, page, attempt, result.http_status,
                len(result.records), result.total_pages,
            )
            if result.http_status == 200 and (
                result.records or (result.total_pages is not None and result.total_pages >= 0)
            ):
                return result
            if attempt < self.settings.search_attempts:
                self._pause(SEARCH_RETRY_PAUSE)
        raise SearchError(
            f"Không đọc được trang thông báo {page} sau {self.settings.search_attempts} lần thử"
        )

    def _download(self, portal: TbPortal, record: ThongBao, downloaded: set[str]) -> None:
        if self.settings.dry_run:
            self.logger.info("Dry-run: bỏ qua tải thông báo %s", record.so_thong_bao or record.message_id)
            return
        if record.message_id in downloaded:
            return
        if self.store.find_existing(record):
            downloaded.add(record.message_id)
            return
        data = portal.download_tb(record)
        if data is None:
            self.logger.error("LỖI TẢI thông báo: %s", record.so_thong_bao or record.message_id)
            return
        if self.store.save(record, data) is not None:
            downloaded.add(record.message_id)


__all__ = ["TbPipeline"]
