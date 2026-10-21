"""Sequential page consumption: download on the current DSE page before advancing."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, Protocol

from .contracts import QueryOutcome, R
from .errors import SchemaChangedError, SearchError
from .run_hooks import RunHooks


class RunContext(Protocol):
    settings: Any
    hooks: RunHooks
    logger: Any
    target_ids: set[str] | None
    downloaded_ids: set[str]
    failed_ids: set[str]
    reused_ids: set[str]
    active_record_id: str
    def _pause(self, seconds: float) -> None: ...
    def _persist(self, records: Any, **kwargs: Any) -> Any: ...


def search_page(context: RunContext, search: Callable[[], QueryOutcome[R]], source: str, page: int) -> QueryOutcome[R]:
    if context.hooks.budget is not None:
        context.hooks.budget.page()
    for attempt in range(1, context.settings.search_attempts + 1):
        context.hooks.check()
        result = search()
        diagnostics = result.diagnostics
        if diagnostics is not None and not diagnostics.complete and diagnostics.status != 'CAPTCHA_INVALID':
            if result.records:
                return result
            raise SchemaChangedError('SCHEMA_CHANGED: ' + '; '.join(diagnostics.reasons))
        context.logger.info('SEARCH %s page=%s try=%s: HTTP=%s records=%s pages=%s',
                            source, page, attempt, result.http_status, len(result.records), result.total_pages)
        if result.http_status == 200 and (result.records or diagnostics is not None and diagnostics.status == 'EMPTY_CONFIRMED'):
            return result
        if attempt < context.settings.search_attempts:
            context._pause(4.0)
    raise SearchError(f'{source}: Không đọc được trang {page} sau {context.settings.search_attempts} lần thử')


def pages(context: RunContext, search: Callable[[int], QueryOutcome[R]], records, source: str) -> Iterator[tuple[int, QueryOutcome[R]]]:
    page, total_pages = 1, None
    seen: set[str] = set()
    while total_pages is None or page <= total_pages:
        context.hooks.check()
        result = search(page)
        known_total = total_pages is not None
        if result.total_pages is not None:
            total_pages = result.total_pages
        keys = {record.record_key for record in result.records}
        new_keys = keys - seen
        context.logger.info('PAGE %s %s: records=%s', source, page, len(result.records))
        if page > 1 and not new_keys:
            if known_total or result.records:
                raise SearchError(f'{source} trang {page}/{total_pages} rỗng hoặc lặp lại; không thể xác nhận đã tra cứu đủ')
            break
        if not result.records and total_pages is not None and total_pages > 1:
            raise SearchError(f'{source} trang {page}/{total_pages} không có hồ sơ')
        seen.update(keys)
        yield page, result
        context._persist(records, force=True)
        if result.diagnostics is not None and not result.diagnostics.complete:
            raise SchemaChangedError('SCHEMA_CHANGED: ' + '; '.join(result.diagnostics.reasons))
        if total_pages is None and not new_keys:
            break
        page += 1
        if total_pages is None or page <= total_pages:
            context._pause(context.settings.pause_between_pages)


def consume_record(context: RunContext, record: R, records, download: Callable[[], Any]) -> bool:
    context.hooks.check()
    key = record.record_key
    context.active_record_id = key
    targeted = context.target_ids is None or key in context.target_ids
    if targeted:
        download()
    if not context.settings.dry_run and targeted:
        if key in context.downloaded_ids:
            context.failed_ids.discard(key)
        else:
            context.failed_ids.add(key)
    context._persist(records)
    state = ('Đã có hợp lệ' if key in context.reused_ids else 'Chỉ tra cứu' if context.settings.dry_run else
             'Đã tải' if key in context.downloaded_ids else 'Lỗi tải' if targeted else 'Chưa tải')
    context.hooks.emit(record=record.to_dict(), discovered=len(records), downloaded=len(context.downloaded_ids),
                       errors=len(context.failed_ids), file_state=state)
    return key in context.downloaded_ids
