"""Đối soát theo lần nộp và xuất CSV/XLSX an toàn.

Mỗi phản hồi một dòng (hồ sơ không có phản hồi vẫn có một dòng trạng thái).
Không suy đoán hồ sơ quá hạn; `Chưa xác định` giữ trung lập. CSV dùng UTF-8 BOM
và escape công thức Excel; XLSX ghi atomic qua ``gdt_tax.export.write_workbook``.
"""
from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from gdt_tax.export import _atomic_write, write_workbook
from gdt_tax.storage import _excel_value

from .documents import FILE_LABELS
from .domain import BUSINESS_LABELS, business_status_from_text, format_date
from .feedback_labels import RESULT_PREFIX, TYPE_LABELS
from .feedback_service import list_feedback_items, submission_key

COLUMNS = [
    ('ma_ho_so', 'Mã hồ sơ'),
    ('nguon', 'Nguồn'),
    ('to_khai', 'Loại tờ khai'),
    ('ky_tinh_thue', 'Kỳ tính thuế'),
    ('ngay_nop', 'Ngày nộp'),
    ('lan_nop', 'Lần nộp'),
    ('cqt_status', 'Trạng thái CQT'),
    ('feedback_count', 'Số phản hồi của hồ sơ'),
    ('feedback_number', 'Số thông báo'),
    ('feedback_type', 'Loại phản hồi'),
    ('feedback_issued_at', 'Ngày thông báo'),
    ('feedback_result', 'Kết quả phản hồi'),
    ('file_status', 'Trạng thái tải'),
    ('integrity', 'Toàn vẹn'),
    ('asset_exists', 'Tệp phản hồi'),
    ('asset_relative_path', 'Đường dẫn tương đối'),
    ('asset_sha256', 'SHA-256 tệp phản hồi'),
    ('pham_vi', 'Phạm vi dữ liệu'),
]
SCOPE_NOTE = ('Kết quả tra cứu hiện tại của tài khoản/tab; chỉ phản ánh dữ liệu đã tải/đọc được, '
              'không xác nhận đầy đủ nghĩa vụ thuế.')
REJECTED_FILL = PatternFill('solid', fgColor='FDECEA')


def _cqt_status(row: dict) -> str:
    raw = str(row.get('trang_thai') or '').strip()
    if raw:
        code = business_status_from_text(raw)
        return BUSINESS_LABELS.get(code, raw) if code != 'unknown' else raw
    code = str(row.get('_cqt_status') or row.get('_notice_state')
               or business_status_from_text(row.get('trang_thai')) or '')
    return str(row.get('_cqt_status_label') or BUSINESS_LABELS.get(code)
               or row.get('trang_thai') or 'Chưa xác định')


def _result_label(result: str) -> str:
    return RESULT_PREFIX.get(result, '') + BUSINESS_LABELS.get(result, 'Chưa xác định')


def reconciliation_rows(rows: list[dict], *, taxpayer_key: str = '',
                        scope_note: str = SCOPE_NOTE) -> list[dict]:
    """Một dòng cho mỗi phản hồi; hồ sơ không có phản hồi vẫn có dòng trạng thái."""
    records: list[dict] = []
    for row in rows:
        items = list_feedback_items(row, taxpayer_key=taxpayer_key)
        base = {
            'ma_ho_so': row.get('ma_ho_so') or '',
            'nguon': row.get('nguon') or '',
            'to_khai': row.get('to_khai') or row.get('ten_tthc') or '',
            'ky_tinh_thue': row.get('ky_tinh_thue') or '',
            'ngay_nop': row.get('ngay_nop') or '',
            'lan_nop': row.get('lan_nop') or row.get('lan_bo_sung') or '',
            'cqt_status': _cqt_status(row),
            'feedback_count': str(len(items)),
            'file_status': FILE_LABELS.get(str(row.get('_file_status') or 'not_downloaded'), 'Chưa tải'),
            'integrity': row.get('_integrity_label') or 'Chưa kiểm tra',
            'pham_vi': scope_note,
            'submission_key': submission_key(row, taxpayer_key=taxpayer_key),
        }
        if not items:
            records.append({**base,
                            'feedback_number': '',
                            'feedback_type': '',
                            'feedback_issued_at': '',
                            'feedback_result': 'Chưa có phản hồi trong dữ liệu hiện có',
                            'asset_exists': '—',
                            'asset_relative_path': '',
                            'asset_sha256': ''})
            continue
        for item in items:
            asset = item.asset
            records.append({**base,
                            'feedback_number': item.feedback.notice_number,
                            'feedback_type': TYPE_LABELS.get(item.feedback.feedback_type,
                                                             TYPE_LABELS.get('unknown', 'Chưa phân loại')),
                            'feedback_issued_at': format_date(item.feedback.issued_at),
                            'feedback_result': _result_label(item.feedback.business_result),
                            'asset_exists': 'Có' if Path(asset.path_or_handle).is_file() else 'Thiếu',
                            'asset_relative_path': item.feedback.source_metadata.get('relative_path', ''),
                            'asset_sha256': asset.checksum})
    return records


def write_reconciliation_csv(path: str | Path, rows: list[dict]) -> Path:
    target = Path(path)
    fieldnames = [key for key, _ in COLUMNS]
    with StringIO(newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _excel_value(row.get(key, '')) for key in fieldnames})
        data = stream.getvalue().encode('utf-8-sig')
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, data)
    return target


def write_reconciliation_xlsx(path: str | Path, rows: list[dict],
                              scope_note: str = SCOPE_NOTE) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Đối soát'
    sheet.append([title for _, title in COLUMNS])
    for record in rows:
        sheet.append([_excel_value(record.get(key, '')) for key, _ in COLUMNS])
        row_index = sheet.max_row
        if (str(record.get('feedback_result', '')).startswith('✕')
                or record.get('cqt_status') == 'Không chấp nhận'):
            for cell in sheet[row_index]:
                cell.fill = REJECTED_FILL
    header_fill = PatternFill('solid', fgColor='225DE9')
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(bold=True, color='FFFFFF')
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    widths = (18, 12, 30, 16, 14, 14, 20, 14, 18, 18, 16, 22, 16, 24, 12, 42, 46, 48)
    for index, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for cells in sheet.iter_rows(min_row=2):
        for cell in cells:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    scope = workbook.create_sheet('Phạm vi')
    scope.append(['Phạm vi dữ liệu', scope_note])
    scope.append(['Số dòng đối soát', len(rows)])
    scope.append(['Số hồ sơ', len({row.get('submission_key') or row.get('ma_ho_so') for row in rows})])
    scope.append(['Ghi chú', 'Không suy đoán hồ sơ quá hạn; "Chưa xác định" là trung lập.'])
    scope.column_dimensions['A'].width = 24
    scope.column_dimensions['B'].width = 100
    for cells in scope.iter_rows(min_row=1):
        for cell in cells:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
    return write_workbook(workbook, Path(path))


__all__ = [
    'COLUMNS',
    'SCOPE_NOTE',
    'reconciliation_rows',
    'write_reconciliation_csv',
    'write_reconciliation_xlsx',
]
