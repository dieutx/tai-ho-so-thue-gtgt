"""Attachment completeness is independent from the committed primary document."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from .errors import GdtError
from .run_hooks import RunCancelled


@dataclass
class AttachmentResult:
    parent_key: str
    status: str = 'PENDING'
    discovered: int = 0
    downloaded: int = 0
    reused: int = 0
    failed: int = 0
    skipped: int = 0
    discovery_failed: int = 0
    items: list[dict] = field(default_factory=list)

    @property
    def complete(self):
        return self.status in {'COMPLETE', 'EMPTY_CONFIRMED', 'NOT_APPLICABLE'}

    def to_dict(self):
        return asdict(self)


def collect_attachments(portal, record, store, hooks, result: AttachmentResult):
    try:
        detail_url, csrf = portal.fetch_detail_csrf(record)
        if not csrf:
            result.discovery_failed = 1
            result.items.append({'code': 'ATTACHMENT_CSRF_MISSING', 'retryable': True})
            return
        listing = portal.fetch_notice_list()
        result.discovered = len(listing.notices)
        if listing.status not in {'PARSED', 'EMPTY_CONFIRMED'}:
            result.discovery_failed = 1
            result.items.append({'code': 'ATTACHMENT_SCHEMA_UNKNOWN', 'retryable': False})
        for notice in listing.notices:
            hooks.check()
            item = {'key': notice.key(record.key).serialize(), 'parent_key': record.record_key,
                    'source': 'tdt' if notice.is_tdt else 'dvc', 'remote_id': notice.id}
            try:
                path = store.find_existing(record.key, notice)
                reused = path is not None
                if path is None:
                    payload = portal.download_notice(notice, detail_url, csrf)
                    path = store.save(record.key, notice, payload) if payload is not None else None
                if path is None:
                    result.failed += 1
                    item.update(status='FAILED', code='ATTACHMENT_INVALID_OR_SAVE_FAILED', retryable=True)
                else:
                    result.reused += int(reused)
                    result.downloaded += int(not reused)
                    item.update(status='REUSED' if reused else 'DOWNLOADED', path=str(path),
                                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size=path.stat().st_size,
                                code='', retryable=False)
            except (GdtError, OSError) as error:
                result.failed += 1
                item.update(status='FAILED', code=getattr(error, 'code', 'ATTACHMENT_' + type(error).__name__.upper()), retryable=True)
            result.items.append(item)
        result.status = ('PARTIAL' if result.failed or result.discovery_failed else
                         'EMPTY_CONFIRMED' if listing.status == 'EMPTY_CONFIRMED' else 'COMPLETE')
    except RunCancelled:
        result.status = 'CANCELLED'
        result.skipped = max(0, result.discovered - result.downloaded - result.reused - result.failed)
        raise
    except (GdtError, OSError) as error:
        result.discovery_failed += 1
        result.items.append({'code': getattr(error, 'code', 'ATTACHMENT_' + type(error).__name__.upper()), 'retryable': True})
    finally:
        if result.status == 'PENDING':
            result.status = 'PARTIAL'


def attachment_sheet(workbook, rows):
    from .spreadsheet_values import append_row
    sheet = workbook.create_sheet('Attachments')
    columns = ('parent_key', 'status', 'discovered', 'downloaded', 'reused', 'failed', 'skipped', 'discovery_failed')
    append_row(sheet, list(columns) + ['key', 'code', 'retryable', 'path', 'sha256', 'size'])
    for row in rows:
        if not row.get('attachment_result'):
            continue
        result = json.loads(row['attachment_result'])
        for item in result.get('items') or [{}]:
            append_row(sheet, [result.get(key, '') for key in columns] +
                       [item.get(key, '') for key in ('key', 'code', 'retryable', 'path', 'sha256', 'size')])
    sheet.freeze_panes = 'A2'
