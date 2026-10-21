from __future__ import annotations

import unittest

from gdt_tax.legacy_notices import parse_legacy_notice_list
from tests.support import fixture


class LegacyNoticeContractsTests(unittest.TestCase):
    def test_notice_namespace_is_accepted_only_as_notice(self):
        from gdt_tax.integrity import validate_xml
        data = b'<TBaoThueDTu xmlns="http://kekhaithue.gdt.gov.vn/TBaoThue"><TBaoThue/></TBaoThueDTu>'
        self.assertTrue(validate_xml(data, 'notice').ok)
        self.assertFalse(validate_xml(data, 'declaration').ok)
        self.assertFalse(validate_xml(data.replace(b'/TBaoThue"', b'/unknown"'), 'notice').ok)

    def test_displayed_notice_reference_is_independent_of_download_id(self):
        html = fixture('etax_legacy_notices.html').replace('>11200000034293775</a>', '>REF-2020-01</a>')
        parsed = parse_legacy_notice_list(html)
        self.assertEqual(parsed.status, 'PARSED')
        self.assertEqual(parsed.notices[0].id, '11200000034293775')

    def test_line_breaks_and_spacing_in_notice_headers_preserve_meaning(self):
        html = fixture('etax_legacy_notices.html').replace('Số thông báo/Mã giao dịch VAN', 'Số thông báo/<br> Mã giao dịch VAN')
        parsed = parse_legacy_notice_list(html)
        self.assertEqual(parsed.status, 'PARSED')
        self.assertEqual(len(parsed.notices), 2)

    def test_unknown_and_paginated_tables_are_never_complete(self):
        html = fixture('etax_legacy_notices.html')
        for value in ('<html/>', html.replace('downloadFile', 'changedHandler'),
                      html.replace('Trang 1/1', 'Trang 1/2'),
                      html.replace('<th>Ngày gửi</th>', '<th>Changed</th>')):
            with self.subTest(value=value[:60]):
                self.assertEqual(parse_legacy_notice_list(value).status, 'SCHEMA_UNKNOWN')

    def test_only_explicit_empty_table_is_confirmed(self):
        html = fixture('etax_legacy_notices.html')
        start, end = html.index('<tbody>'), html.index('</tbody>')
        html = html[:start] + '<tbody>' + html[end:]
        self.assertEqual(parse_legacy_notice_list(html).status, 'SCHEMA_UNKNOWN')
        html = html.replace('Có 2 bản ghi', 'Có 0 bản ghi')
        self.assertEqual(parse_legacy_notice_list(html).status, 'EMPTY_CONFIRMED')

    def test_combined_acceptance_heading_does_not_claim_rejection(self):
        notice = parse_legacy_notice_list(fixture('etax_legacy_notices.html')).notices[0]
        self.assertEqual(notice.loai, 'khac')
