"""Synthetic portal regressions executed by both source and frozen smoke."""
from types import SimpleNamespace

from gdt_tax.auth_outcomes import AuthOutcome, classify_response
from gdt_tax.gnt.parsing import parse_gnt_table
from gdt_tax.parsing import parse_record_table
from gdt_tax.table_contracts import SCHEMAS


def portal_regression_check() -> bool:
    html = '<div style="display:none"><span style="color:red">invalid credentials</span></div><p>invalid captcha</p>'
    response = SimpleNamespace(content=html.encode(), text=html, status_code=200, headers={})
    if classify_response(response, 'ETAX_LEGACY') != AuthOutcome.CAPTCHA_INVALID:
        raise AssertionError('Nested hidden authentication markup failed')
    labels = list(SCHEMAS['GNT'].labels)
    labels[12:14] = [label for label, _ in SCHEMAS['GNT'].extra_labels]
    cells = ['1', 'synthetic-ref', '', '', '<a href="javascript:chiTietCT(900000001)">synthetic-gnt</a>',
             '100', 'VND', 'synthetic', '', '01/09/2026', '', '', '', '', '', '', '', '',
             '<a href="javascript:downloadGNT(900000001)">download</a>', '']
    html = '<table id="data_content_onday"><thead><tr>' + ''.join('<td>'+label+'</td>' for label in labels)
    html += '</tr></thead><tbody><tr>' + ''.join('<td>'+value+'</td>' for value in cells) + '</tr>'
    html += '<tr><td colspan="5">Tổng tiền:</td><td>100</td><td>VND</td><td colspan="13"></td></tr></tbody></table>'
    parsed = parse_gnt_table(html)
    if parsed.diagnostics.status != 'PARSED' or len(parsed.records) != 1 or parsed.records[0].so_tien != '100':
        raise AssertionError('GNT heading/footer regression failed')
    # Public heading observed on DVC 22/10/2026; all record values are synthetic.
    labels = ['STT', 'Thao tác', 'Mã hồ sơ', 'Tên TTHC', 'Tờ khai', 'Kỳ tính thuế',
              'Loại tờ khai', 'Lần nộp bổ sung', 'Lần nộp (Tờ khai)/File số (DLVC)',
              'Cơ quan thuế tiếp nhận', 'Ngày nộp', 'Trạng thái', 'Hồ sơ đính kèm']
    cells = ['1', '<i data-ma-ho-so="SYNTHETIC-DVC-1"></i>', 'SYNTHETIC-DVC-1',
             'synthetic-procedure', 'synthetic-declaration', '09/2026', 'synthetic-type',
             '2', '3', 'synthetic-office', '22/10/2026', 'synthetic-status', '0']
    html = '<div id="table-container"><table><thead><tr>'
    html += ''.join('<th rowspan="2">' + label + '</th>' for label in labels)
    # Live DVC rows can omit the final optional attachment cell.
    html += '</tr></thead><tbody><tr>' + ''.join('<td>' + value + '</td>' for value in cells[:-1])
    html += '</tr></tbody></table></div>'
    parsed = parse_record_table(html, 'DVC')
    if (parsed.diagnostics.status != 'PARSED' or len(parsed.records) != 1
            or parsed.records[0].ma_ho_so != 'SYNTHETIC-DVC-1'
            or parsed.records[0].lan_nop != '3' or parsed.records[0].lan_bo_sung != '2'):
        raise AssertionError('DVC submission/file heading regression failed')
    return True
