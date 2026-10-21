"""Synthetic portal regressions executed by both source and frozen smoke."""
from types import SimpleNamespace

from gdt_tax.auth_outcomes import AuthOutcome, classify_response
from gdt_tax.gnt.parsing import parse_gnt_table
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
    return True
