"""Export local notice references without copying the original attachments."""
from __future__ import annotations

import re

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .notices import REFERENCE_LABELS, STATE_LABELS


def notice_report_sheet(workbook, rows, hooks):
    sheet = workbook.create_sheet('Thông báo tờ khai')
    columns = [('ma_ho_so', 'Mã hồ sơ'), ('nguon', 'Nguồn tờ khai'),
               ('parent_key', 'Khóa hồ sơ'), ('state', 'Trạng thái thông báo'),
               ('so_thong_bao', 'Số thông báo'), ('ngay_thong_bao', 'Ngày thông báo'),
               ('ten_thong_bao', 'Tên thông báo'), ('ly_do', 'Lý do'),
               ('relative_path', 'Đường dẫn từ nơi lưu tờ khai'),
               ('reference_key', 'Khóa tham chiếu thông báo'), ('sha256', 'SHA-256 tệp'),
               ('size', 'Dung lượng byte'), ('reference_status', 'Đối chiếu tham chiếu')]

    def append(values):
        clean = [re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '\ufffd', value)
                 if isinstance(value, str) else value for value in values]
        sheet.append(clean)
        for cell, value in zip(sheet[sheet.max_row], clean, strict=True):
            if isinstance(value, str):
                cell.data_type = 's'

    append([label for _, label in columns])
    for row in rows:
        for notice in row.get('_notices') or []:
            hooks.check()
            item = {**notice, 'ma_ho_so': row.get('ma_ho_so', ''), 'nguon': row.get('nguon', ''),
                    'parent_key': row.get('record_key') or notice.get('parent_key', ''),
                    'state': STATE_LABELS.get(notice.get('state'), 'Chưa xác định'),
                    'reference_status': REFERENCE_LABELS.get(notice.get('reference_status'), 'Chưa xác định')}
            append([item.get(key, '') for key, _ in columns])
    for cell in sheet[1]:
        cell.fill = PatternFill('solid', fgColor='225DE9')
        cell.font = Font(bold=True, color='FFFFFF')
    for index, (key, _) in enumerate(columns, 1):
        sheet.column_dimensions[get_column_letter(index)].width = 55 if key in {'relative_path', 'ly_do', 'ten_thong_bao'} else 26
    for cells in sheet.iter_rows(min_row=2):
        for cell in cells:
            cell.alignment = Alignment(vertical='top', wrap_text=True)
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    return sheet
