"""Explicit local export of the current result; no query/download/network."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from gdt_tax.attachments import attachment_sheet
from gdt_tax.export import write_workbook
from gdt_tax.spreadsheet_values import append_row
from gdt_tax.storage import _excel_value

from .documents import FILE_LABELS, KINDS, counters, verify_rows
from .notice_reports import notice_report_sheet
from .services import JobResult


def export_document_report(config, hooks):
    rows = verify_rows(config.mode, config.input_rows, config.source or config.output, hooks)
    identifiers = {'tax': [('ma_ho_so', 'Mã hồ sơ'), ('to_khai', 'Tờ khai'), ('ky_tinh_thue', 'Kỳ'), ('ngay_nop', 'Ngày nộp')],
                   'gnt': [('ctu_id', 'Mã chứng từ'), ('so_gnt', 'Số GNT'), ('ngay_lap', 'Ngày lập'), ('so_tien', 'Số tiền gốc'), ('loai_tien', 'Loại tiền')],
                   'notice': [('message_id', 'Mã thông báo'), ('so_thong_bao', 'Số thông báo'), ('ten_thong_bao', 'Tên thông báo'), ('ngay_gui', 'Ngày gửi')]}
    notice_columns = [('_notice_summary', 'Phản hồi CQT'), ('_notice_count', 'Số phản hồi')] if config.mode == 'tax' else []
    columns = identifiers[config.mode] + notice_columns + [('trang_thai', 'Trạng thái cơ quan thuế'), ('_file_label', 'Trạng thái tệp'),
        (KINDS[config.mode][2], 'Tên tệp'), ('_file_path', 'Đường dẫn thực'), ('_file_size', 'Dung lượng byte'),
        ('_file_hash', 'SHA-256'), ('_error_message', 'Lỗi tải'), ('_file_reason', 'Ghi chú')]
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Danh sách hồ sơ'
    append_row(sheet, [title for _, title in columns])
    for row in rows:
        hooks.check()
        row['_file_label'] = FILE_LABELS.get(row.get('_file_status'), 'Chưa tải')
        row['_notice_count'] = len(row.get('_notices') or [])
        append_row(sheet, [_excel_value(row.get(key)) for key, _ in columns])
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.fill = PatternFill('solid', fgColor='225DE9')
        cell.font = Font(bold=True, color='FFFFFF')
    for index, (key, _) in enumerate(columns, 1):
        sheet.column_dimensions[get_column_letter(index)].width = 60 if key in {'_file_path', '_error_message', '_file_reason'} else 25
    summary = workbook.create_sheet('Tổng kết')
    append_row(summary, ['Thông tin', 'Giá trị'])
    count = counters(rows)
    for key, value in [('Tài khoản', config.username), ('Từ ngày', config.from_date), ('Đến ngày', config.to_date),
                       ('Tìm thấy', count['found']), ('Đã tải hợp lệ', count['downloaded']), ('Chưa tải', count['pending']),
                       ('Tải lỗi', count['failed']), ('Nguồn tệp', str(config.source or config.output)),
                       ('Phạm vi', 'Toàn bộ kết quả hiện tại; không phụ thuộc bộ lọc bảng. Không sao chép tệp gốc.')]:
        append_row(summary, [key, _excel_value(value)])
    summary.column_dimensions['A'].width = 28
    summary.column_dimensions['B'].width = 90
    attachment_sheet(workbook, rows)
    if config.mode == 'tax':
        notice_report_sheet(workbook, rows, hooks)
    hooks.check()
    path = write_workbook(workbook, config.report_path)
    return JobResult('SUCCESS', 'Đã xuất danh sách Excel; tệp hồ sơ gốc giữ nguyên', config.output,
                     rows=rows, files=[path], discovered=len(rows))
