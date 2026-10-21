"""Luồng tra cứu — tải XML giấy nộp tiền, không parse nội dung GNT.

Bám theo :class:`gdt_tax.pipeline.Pipeline` nhưng đơn giản hơn: chỉ một nguồn
(trang Thuế điện tử cũ), tra cứu theo khoảng ngày lập GNT và tải ngay trên từng
trang vì cổng chỉ giữ danh sách của trang gần nhất trong phiên.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from functools import partial

from ..catalog import CatalogCheckpoint, flush_on_error
from ..contracts import QueryOutcome
from ..errors import NetworkError
from ..http import HttpClient
from ..identity import account_fingerprint, scope_targets
from ..orchestration import consume_record, pages, search_page
from ..ownership import prepare_output
from ..run_hooks import RunBudget, RunHooks
from .models import GiayNopTien, GntSummary, gnt_periods
from .portal import GntPortal
from .storage import GntStore, write_gnt_metadata

LOGGER_NAME = "gdt_tax.gnt.pipeline"
SEARCH_RETRY_PAUSE = 4.0


class GntPipeline:
    """Tra cứu và tải giấy nộp tiền theo từng đoạn ngày, lưu XML + danh mục."""

    def __init__(
        self,
        settings,
        http: HttpClient,
        captcha,
        *,
        store: GntStore | None = None,
        portal_factory: Callable[[], GntPortal] | None = None,
        logger: logging.Logger | None = None,
        sleep: Callable[[float], None] = time.sleep,
        hooks: RunHooks | None = None,
        persist_metadata: bool = True,
        target_ids: set[str] | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.captcha = captcha
        self.store = store or GntStore(settings.download_dir)
        self.portal_factory = portal_factory
        self.logger = logger or logging.getLogger(LOGGER_NAME)
        self.sleep = sleep
        inherited_hooks = getattr(http, "hooks", None)
        self.hooks: RunHooks = hooks or (inherited_hooks if isinstance(inherited_hooks, RunHooks) else RunHooks())
        if self.hooks.budget is None:
            self.hooks.budget = RunBudget()
        self.persist_metadata = persist_metadata
        self.checkpoint = CatalogCheckpoint(write_gnt_metadata, settings.download_dir,
                                            enabled=persist_metadata and not settings.dry_run)
        self.target_ids = target_ids
        self.account_key = account_fingerprint(settings.username)
        self.record_errors: dict[str, str] = {}
        self.active_record_id = ""
        self.records: dict = {}
        self.downloaded_ids: set[str] = set()
        self.failed_ids: set[str] = set()
        self.reused_ids: set[str] = set()

    def _persist(self, records, **kwargs):
        return self.checkpoint.persist(records, **kwargs)

    def _attempt_download(self, portal, record, downloaded):
        try:
            return self._download(portal, record, downloaded)
        except NetworkError as error:
            if self.target_ids is None:
                raise
            self.record_errors[record.record_key] = str(error)
            self.logger.error("Không tải được GNT %s: %s", record.ctu_id, error)

    @flush_on_error
    def run(self) -> GntSummary:
        self.record_errors = {}
        self.active_record_id = ""
        self.records = {}
        self.downloaded_ids = set()
        self.failed_ids = set()
        self.reused_ids = set()
        if self.target_ids is not None:
            self.target_ids = scope_targets(self.target_ids, account_key=self.account_key,
                                           sources=["GNT"], document_kind="GNT")
        prepare_output(self.settings)
        summary = GntSummary(dry_run=self.settings.dry_run)
        periods = gnt_periods(
            self.settings.from_date, self.settings.to_date, self.settings.max_days_per_search
        )
        self.logger.info(
            "Bắt đầu tra cứu giấy nộp tiền: %s → %s (%s đoạn)",
            self.settings.from_date.strftime("%d/%m/%Y"),
            self.settings.to_date.strftime("%d/%m/%Y"),
            len(periods),
        )
        portal = self.portal_factory() if self.portal_factory else GntPortal(
            self.http, self.captcha, self.settings, self.logger
        )

        records: dict[str, GiayNopTien] = self.records
        downloaded: set[str] = self.downloaded_ids
        for period in periods:
            self.hooks.check()
            summary.periods += 1
            self.logger.info("=== GNT: %s ===", period.label)
            self._search_period(portal, period, records, downloaded)
            if self.target_ids and self.target_ids.issubset(downloaded):
                break

        if self._persist(records, materialize=True):
            self.logger.info(
                "GNT: đã ghi danh sách giấy nộp tiền (CSV/JSON/Excel)"
            )
        summary.discovered = len(records)
        summary.downloaded = len(downloaded)
        summary.expected = len(self.target_ids) if self.target_ids is not None else len(records)
        return summary

    def _search_period(
        self,
        portal: GntPortal,
        period,
        records: dict[str, GiayNopTien],
        downloaded: set[str],
    ) -> None:
        for page, result in pages(self, lambda number: self._search_page(portal, period, number), records, 'GNT'):
            for index, found in enumerate(result.records, start=1):
                self.hooks.check()
                found.account_key = self.account_key
                record = records.setdefault(found.record_key, found)
                self.logger.info(
                    "TẢI trang=%s mục=%s/%s: %s",
                    page, index, len(result.records), found.so_gnt or found.ctu_id,
                )
                consume_record(self, record, records, partial(self._attempt_download, portal, record, downloaded))
                if self.target_ids and self.target_ids.issubset(downloaded):
                    if result.diagnostics is None or result.diagnostics.complete:
                        return
                self._pause(self.settings.pause_between_records)

    def _pause(self, seconds: float) -> None:
        jitter = self.settings.pause_jitter
        delay = seconds * (1 + random.uniform(0, jitter)) if jitter > 0 and seconds > 0 else seconds
        self.hooks.pause(delay, self.sleep)

    def _search_page(self, portal: GntPortal, period, page: int) -> QueryOutcome[GiayNopTien]:
        return search_page(self, lambda: portal.search_gnt(period, page), 'GNT', page)

    def _download(self, portal: GntPortal, record: GiayNopTien, downloaded: set[str]) -> None:
        if self.settings.dry_run:
            self.logger.info("Dry-run: bỏ qua tải GNT %s", record.so_gnt or record.ctu_id)
            return
        if record.record_key in downloaded:
            return
        if self.store.find_existing(record):
            self.reused_ids.add(record.record_key)
            downloaded.add(record.record_key)
            return
        data = portal.download_gnt(record)
        if data is None:
            self.record_errors[record.record_key] = getattr(portal, "last_download_error", "") or "Cổng không trả XML hoàn chỉnh. Kiểm tra kết nối/phiên đăng nhập rồi thử lại."
            self.logger.error("LỖI TẢI GNT: %s", record.so_gnt or record.ctu_id)
            return
        if self.store.save(record, data) is not None:
            downloaded.add(record.record_key)
        else:
            self.record_errors[record.record_key] = "Dữ liệu nhận được không phải XML hoàn chỉnh/hợp lệ; tệp chưa được lưu."


__all__ = ["GntPipeline"]
