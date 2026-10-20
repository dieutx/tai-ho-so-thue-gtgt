"""Presentation of real records; disk state is independent of tax status.

Verification is read-only and runs in the worker. Core metadata remains the
source of document fields; UI fields are prefixed with an underscore.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import fields
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from gdt_tax.gnt.models import GiayNopTien
from gdt_tax.gnt.naming import gnt_xml_filename
from gdt_tax.gnt.portal import is_gnt_xml
from gdt_tax.integrity import (
    candidate_paths,
    matches_evidence,
    read_bounded,
    source_reference,
    valid_declaration_zip,
)
from gdt_tax.models import CaseRecord
from gdt_tax.naming import zip_filename
from gdt_tax.run_hooks import RunHooks
from gdt_tax.tb.models import ThongBao
from gdt_tax.tb.naming import tb_pdf_filename
from gdt_tax.tb.portal import is_tb_pdf

KINDS = {
    'tax': (CaseRecord, 'ma_ho_so', 'tep_zip', 'ngay_nop', zip_filename, valid_declaration_zip),
    'gnt': (GiayNopTien, 'ctu_id', 'tep_xml', 'ngay_lap', gnt_xml_filename, is_gnt_xml),
    'notice': (ThongBao, 'message_id', 'tep_pdf', 'ngay_gui', tb_pdf_filename, is_tb_pdf),
}
FILE_LABELS = {'not_downloaded': 'Chưa tải', 'queued': 'Đang chờ', 'downloading': 'Đang tải',
               'downloaded': 'Đã tải', 'failed': 'Tải lỗi', 'skipped': 'Bỏ qua'}


def document_id(mode: str, row: dict) -> str:
    return str(row.get(KINDS[mode][1], '')) if mode in KINDS else str(row.get('artifact_id', ''))


def record_from_row(mode: str, row: dict):
    kind = KINDS[mode][0]
    return kind(**{field.name: row[field.name] for field in fields(kind) if field.name in row})


def event_datetime(value: Any) -> datetime:
    raw = str(value or '').strip()
    for pattern in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y',
                    '%d-%m-%Y %H:%M:%S', '%d-%m-%Y', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def amount_value(value: Any) -> Decimal | None:
    raw = re.sub(r'(?i)\b(?:VND|VNĐ)\b|[₫đ$€\s]', '', str(value if value is not None else '')).replace('−', '-')
    if not re.fullmatch(r'[0-9.,()\-+]+', raw):
        return None
    if not raw:
        return None
    if raw.startswith('(') and raw.endswith(')'):
        raw = '-' + raw[1:-1]
    if '.' in raw and ',' in raw:
        raw = raw.replace('.', '').replace(',', '.') if raw.rfind(',') > raw.rfind('.') else raw.replace(',', '')
    elif re.fullmatch(r'[+-]?\d{1,3}(?:[.,]\d{3})+', raw):
        raw = raw.replace('.', '').replace(',', '')
    else:
        raw = raw.replace(',', '.')
    try:
        result = Decimal(raw)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def display_amount(value: Any, currency: str = '') -> str:
    number = amount_value(value)
    if number is None:
        return str(value or '—')
    whole, _, fraction = format(abs(number), 'f').partition('.')
    grouped = f'{int(whole):,}'.replace(',', '.')
    text = ('-' if number < 0 else '') + grouped + (',' + fraction if fraction else '')
    return text + (' ₫' if not currency or currency.upper() in {'VND', 'VNĐ', 'Đ'} else ' ' + currency)


def needs_review(row: dict) -> bool:
    status = str(row.get('trang_thai', '')).casefold()
    return any(marker in status for marker in ('từ chối', 'không chấp nhận', 'không được chấp nhận', 'không thành công'))


def counters(rows: list[dict]) -> dict[str, int]:
    return {'found': len(rows), 'downloaded': sum(r.get('_file_status') == 'downloaded' for r in rows),
            'failed': sum(r.get('_file_status') == 'failed' for r in rows),
            'pending': sum(r.get('_file_status', 'not_downloaded') in {'not_downloaded', 'queued', 'downloading'} for r in rows)}


def verify_rows(mode: str, rows: list[dict], output: Path, hooks: RunHooks | None = None,
                *, failed_ids: set[str] | None = None, errors: dict[str, str] | None = None,
                reused_ids: set[str] | None = None) -> list[dict]:
    """Validate actual files without creating, moving, renaming or rewriting them."""
    if mode not in KINDS:
        return rows
    hooks = hooks or RunHooks()
    root = output.resolve()
    _, id_field, file_field, _, naming, valid = KINDS[mode]
    zip_candidates = list(output.glob('*.zip')) if mode == 'tax' else []
    verified = []
    for original in rows:
        hooks.check()
        row = dict(original)
        key = str(row.get(id_field, ''))
        record = record_from_row(mode, row)
        names = [str(row.get(file_field) or ''), naming(record)]
        candidates = [output / name for name in names if name]
        candidates.extend(candidate_paths(output / naming(record)))
        if mode == 'tax':
            candidates.extend(p for p in zip_candidates if p.stem == key or p.name.startswith((key + '__', key + '-')))
        row.update(_file_status='not_downloaded', _file_path='', _file_size=0, _file_hash='', _file_updated='',
                   _file_reason='', _error_message='')
        seen = set()
        for path in candidates:
            resolved = path.resolve()
            if resolved in seen or not resolved.is_relative_to(root) or not path.is_file():
                continue
            seen.add(resolved)
            try:
                if path.stat().st_size > 256 * 1024 * 1024:
                    row['_file_reason'] = 'Tệp vượt giới hạn kiểm tra; chưa xác nhận hoàn chỉnh'
                    continue
                content = read_bounded(path, 256 * 1024 * 1024)
                kind = {"tax": "zip", "gnt": "gnt", "notice": "pdf"}[mode]
                if not valid(content) or not matches_evidence(path, content, source_reference(record, kind)):
                    row['_file_reason'] = 'Tệp hiện có không hoàn chỉnh hoặc sai định dạng; có thể tải lại'
                    continue
                row.update(_file_status='downloaded', _file_path=str(resolved), _file_size=len(content),
                           _file_hash=hashlib.sha256(content).hexdigest(),
                           _file_updated=datetime.fromtimestamp(path.stat().st_mtime).strftime('%d/%m/%Y %H:%M:%S'))
                row[file_field] = path.name
                if reused_ids and key in reused_ids:
                    row['_file_reason'] = 'Đã có tệp hợp lệ; bỏ qua tải lại'
                break
            except OSError:
                row['_file_reason'] = 'Không đọc được tệp hiện có; kiểm tra quyền hoặc tải lại'
        if row['_file_status'] != 'downloaded':
            if (failed_ids and key in failed_ids) or (failed_ids is None and original.get('_file_status') == 'failed'):
                row['_file_status'] = 'failed'
                row['_error_message'] = (errors or {}).get(key) or original.get('_error_message') or 'Tải chưa thành công. Kiểm tra kết nối/phiên và thử lại tệp này.'
            elif original.get('_file_status') == 'downloaded':
                row['_file_reason'] = 'Tệp không còn ở nơi lưu hoặc không còn hợp lệ; có thể đã bị xóa/di chuyển'
        row['_file_state'] = FILE_LABELS[row['_file_status']]
        row['_needs_review'] = needs_review(row)
        verified.append(row)
    return verified
