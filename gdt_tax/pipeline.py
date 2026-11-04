"""Lập kế hoạch, đăng nhập theo nguồn và tải ngay trong từng trang kết quả."""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial

from .attachments import AttachmentResult, collect_attachments
from .auth import login, open_landing
from .catalog import CatalogCheckpoint, flush_on_error
from .classification import classify_record
from .constants import METADATA_CSV, METADATA_JSON, METADATA_XLSX, SOURCE_ETAX_LEGACY
from .contracts import DownloadArtifact, QueryOutcome, checked_artifact
from .csrf import csrf_token
from .dates import format_date
from .dvc_notices import NOTICE_DIRECTORY, NoticeStore
from .errors import LoginError, NetworkError, SchemaChangedError, SearchError
from .http import HttpClient
from .identity import RecordKey, account_fingerprint, scope_targets
from .models import CaseRecord, RunSummary
from .orchestration import consume_record, pages, search_page
from .ownership import prepare_output
from .portal_profiles import profile_for
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
        download_notices: bool = True,
        authenticate: bool = True,
        input_rows: list[dict] | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.captcha = captcha
        self.store = store or ZipStore(settings.download_dir)
        self.portal_factory = portal_factory
        self.logger = logger or logging.getLogger(LOGGER_NAME)
        self.sleep = sleep
        inherited_hooks = getattr(http, "hooks", None)
        self.hooks: RunHooks = hooks or (inherited_hooks if isinstance(inherited_hooks, RunHooks) else RunHooks())
        if self.hooks.budget is None:
            self.hooks.budget = RunBudget()
        self.persist_metadata = persist_metadata
        self.checkpoint = CatalogCheckpoint(write_metadata, settings.download_dir,
                                            enabled=persist_metadata and not settings.dry_run)
        self.target_ids = target_ids
        self.input_rows = {row.get('record_key'): row for row in input_rows or []}
        self.account_key = account_fingerprint(settings.username)
        self.case_targets: set[str] | None = None
        self.record_errors: dict[str, str] = {}
        self.active_record_id = ""
        self.records: dict = {}
        self.downloaded_ids: set[str] = set()
        self.failed_ids: set[str] = set()
        self.reused_ids: set[str] = set()
        self.download_notices = download_notices
        #: Có thể bỏ qua bước đăng nhập khi phiên DVC đã được xác thực trước đó.
        self.authenticate = authenticate
        self.notice_store = NoticeStore(settings.download_dir / NOTICE_DIRECTORY)
        self.attachments: dict[str, AttachmentResult] = {}

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
        self.attachments = {}
        summary = RunSummary(dry_run=self.settings.dry_run)
        plan = self.settings.execution_plan()
        summary.routing_version = plan.version
        summary.profile_versions = {source: profile_for(self.settings, source).version for source in ('DVC', 'ETAX', 'ETAX_LEGACY', 'GNT', 'TB')}
        summary.routing_issues = plan.issues
        summary.skipped_periods = sum(issue['code'] in {'ROUTING_GAP', 'ROUTING_OVERLAP'} for issue in plan.issues)
        self.logger.info('EXECUTION_PLAN: routing=%s profile=%s periods=%s issues=%s',
                         plan.version, json.dumps(summary.profile_versions, sort_keys=True),
                         json.dumps([{'source': p.source, 'start': p.start.isoformat(), 'end': p.end.isoformat()}
                                     for p in plan.periods], sort_keys=True),
                         json.dumps(plan.issues, sort_keys=True))
        self.logger.info(
            "Bắt đầu: %s → %s (cutoff %s; DVC %s)",
            format_date(self.settings.from_date), format_date(self.settings.to_date),
            format_date(self.settings.etax_cutoff),
            "bật" if self.settings.dvc_enabled else "tạm tắt",
        )
        active = []
        for period in plan.periods:
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
            if self.authenticate and not login(self.http, self.captcha, self.settings, self.logger):
                raise LoginError("ĐĂNG NHẬP THẤT BẠI")
            landing = open_landing(self.http, self.logger, profile=self.settings.header_profile)
            csrf = csrf_token(landing)
        portals = self.portal_factory(self.http, self.captcha, self.settings, csrf, self.logger)

        records: dict[str, CaseRecord] = self.records
        succeeded: set[str] = self.downloaded_ids
        attempted: set[str] = set()
        for period in active:
            self.hooks.check()
            summary.periods += 1
            self.logger.info("=== %s: %s ===", period.source, period.label)
            portal = portals[period.source]
            targets = self.target_ids if self.target_ids is not None else self.case_targets
            if targets is not None and getattr(portal, 'supports_case_search', False):
                for token in sorted(targets - attempted):
                    key = RecordKey.parse(token)
                    if key.source != period.source:
                        continue
                    raw_date = str(self.input_rows.get(token, {}).get('ngay_nop') or '')
                    try:
                        submitted = datetime.strptime(raw_date[:10], '%d/%m/%Y').date()
                    except ValueError:
                        submitted = None
                    # A stale/imported date is an optimisation hint, never a
                    # reason to silently omit an explicitly selected ID.
                    if submitted is not None and not self.settings.from_date <= submitted <= self.settings.to_date:
                        submitted = None
                    if submitted is not None and not period.start <= submitted <= period.end:
                        continue
                    self.logger.info('TRA CỨU THEO MÃ: %s — %s', period.source, key.remote_id)
                    self._search_and_download(portal, period, records, succeeded, case_id=key.remote_id)
                    if token in records:
                        attempted.add(token)
                    self.hooks.check()
                continue
            if self._search_and_download(portal, period, records, succeeded):
                break

        if self._persist(records, materialize=True):
            self.logger.info(
                "Metadata: %s, %s và %s; danh mục nhóm: phan_loai_ho_so.json",
                METADATA_CSV, METADATA_JSON, METADATA_XLSX,
            )
        summary.downloaded = len(succeeded)
        summary.discovered = len(records)
        summary.expected = len(self.target_ids) if self.target_ids is not None else 1 if self.settings.case_id else len(records)
        summary.attachments_complete = all(item.complete for item in self.attachments.values())
        summary.attachments_discovered = sum(item.discovered for item in self.attachments.values())
        summary.attachments_downloaded = sum(item.downloaded for item in self.attachments.values())
        summary.attachments_reused = sum(item.reused for item in self.attachments.values())
        summary.attachments_failed = sum(item.failed + item.discovery_failed for item in self.attachments.values())
        return summary

    def _search_and_download(self, portal, period, records, succeeded, *, case_id: str = '') -> bool:
        for page, result in pages(self, lambda number: self._search_page(portal, period, number, case_id=case_id), records, portal.source):
            for index, found in enumerate(result.records, start=1):
                self.hooks.check()
                if found.nguon != period.source:
                    raise SchemaChangedError("RECORD_SOURCE_OUTSIDE_PLAN")
                found.account_key = self.account_key
                found.portal_profile_version = profile_for(self.settings, period.source).version
                found.routing_version = (self.settings.routing_policy or self.settings.execution_plan()).version
                if self.case_targets is not None and found.record_key not in self.case_targets:
                    continue
                if self.target_ids is not None and found.record_key not in self.target_ids:
                    continue
                if case_id and found.ma_ho_so != case_id:
                    continue
                found.trang_thai_tra_cuu = found.trang_thai
                found.trang_thai_cap_nhat = datetime.now(timezone.utc).isoformat()
                record = records.setdefault(found.record_key, classify_record(found))
                self.logger.info("TẢI trang=%s mục=%s/%s: %s", page, index, len(result.records), record.ma_ho_so)
                success = consume_record(self, record, records, partial(self._attempt_download, portal, record, succeeded))
                if case_id and (result.diagnostics is None or result.diagnostics.complete):
                    return True
                if self.settings.case_id and (success or self.settings.dry_run):
                    if result.diagnostics is None or result.diagnostics.complete:
                        return True
                if self.target_ids and self.target_ids.issubset(succeeded):
                    if result.diagnostics is None or result.diagnostics.complete:
                        return True
                self._pause(self.settings.pause_between_records)
            if case_id:
                if result.diagnostics is not None and not result.diagnostics.complete:
                    raise SchemaChangedError('SCHEMA_CHANGED: ' + '; '.join(result.diagnostics.reasons))
                # A single ID query must never fall back to scanning unrelated pages.
                if result.records or (result.total_pages or 0) > 1:
                    raise SearchError('CASE_SEARCH_NOT_SCOPED: Cổng trả kết quả ngoài mã hồ sơ đang tra cứu; đã dừng quét trang.')
                return False
        return False

    def _pause(self, seconds: float) -> None:
        jitter = self.settings.pause_jitter
        delay = seconds * (1 + random.uniform(0, jitter)) if jitter > 0 and seconds > 0 else seconds
        self.hooks.pause(delay, self.sleep)

    def _search_page(self, portal, period, page: int, *, case_id: str = '') -> QueryOutcome[CaseRecord]:
        return search_page(self, lambda: portal.search(period, page, case_id=case_id) if case_id else portal.search(period, page), portal.source, page)

    def _download(self, portal, record: CaseRecord, succeeded: set[str]) -> bool:
        # Dry-run không được dò/đổi tên file đã có hoặc tính chúng là vừa tải.
        if self.settings.dry_run:
            self.logger.info("Dry-run: bỏ qua tải %s", record.ma_ho_so)
            return False
        if record.record_key in succeeded:
            return True
        if self.store.find_existing(record):
            self.reused_ids.add(record.record_key)
            if record.nguon == 'DVC':
                detail_url, csrf = portal.fetch_detail_csrf(record)
                self._download_attachments(portal, record, detail_url=detail_url, csrf=csrf)
            else:
                self._download_attachments(portal, record)
            succeeded.add(record.record_key)
            return True
        detail_url, csrf = portal.fetch_detail_csrf(record)
        if not csrf and not getattr(portal, "csrf_optional", False):
            self.record_errors[record.record_key] = "Cổng không trả mã xác thực CSRF cho tệp. Kiểm tra phiên đăng nhập rồi thử lại."
            self.logger.error("LỖI TẢI: không lấy được CSRF token cho %s", record.ma_ho_so)
            return False
        response = portal.download(record, detail_url, csrf)
        if isinstance(response, DownloadArtifact):
            if response.media_kind != 'zip':
                raise SearchError('DOWNLOAD_ARTIFACT_KIND_MISMATCH')
            path = self.store.save(record, checked_artifact(response, record))
            if path is None:
                self.record_errors[record.record_key] = 'DOWNLOAD_ARTIFACT_INVALID'
                return False
            succeeded.add(record.record_key)
            self._download_attachments(portal, record, detail_url=detail_url, csrf=csrf)
            return True
        if response is None or response.status_code != 200:
            self.record_errors[record.record_key] = f"Cổng trả HTTP {getattr(response, 'status_code', 'không có phản hồi')} khi tải tệp. Kiểm tra kết nối/phiên rồi thử lại."
            self.logger.error("LỖI TẢI: %s HTTP=%s", record.ma_ho_so, getattr(response, "status_code", "-"))
            return False
        if self.store.save_from_response(record, response) is None:
            code = getattr(self.store, "last_error", "")
            if code and code != "ZIP_DECODE_FAILED":
                self.record_errors[record.record_key] = (
                    f"Tệp cổng trả về là ZIP hợp lệ nhưng không đúng loại hồ sơ ({code}); "
                    "tệp chưa được lưu."
                )
            else:
                self.record_errors[record.record_key] = (
                    "Dữ liệu trả về không phải ZIP hoàn chỉnh/hợp lệ. "
                    "Tệp chưa được lưu; có thể phiên đã hết hạn."
                )
            # Không để hồ sơ thiếu tệp mà không có lý do trong nhật ký.
            self.logger.error("LỖI TẢI: %s — %s", record.ma_ho_so,
                              self.record_errors[record.record_key])
            return False
        succeeded.add(record.record_key)
        self._download_attachments(portal, record, detail_url=detail_url, csrf=csrf)
        return True

    def _download_attachments(self, portal, record, *, detail_url=None, csrf=None):
        if not self.download_notices or not callable(getattr(portal, 'fetch_notice_list', None)):
            return
        result = AttachmentResult(record.record_key)
        self.attachments[record.record_key] = result
        try:
            collect_attachments(portal, record, self.notice_store, self.hooks, result,
                                detail_url=detail_url, csrf=csrf)
        finally:
            record.attachment_status = result.status
            record.attachment_result = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)
            self.logger.info('ATTACHMENTS: status=%s discovered=%s downloaded=%s reused=%s failed=%s',
                result.status, result.discovered, result.downloaded, result.reused, result.failed + result.discovery_failed)


__all__ = ["Pipeline"]
