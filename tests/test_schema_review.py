"""Cross-adapter regressions from the 22/10 schema review; no live data/network."""
from __future__ import annotations

import unittest
from unittest.mock import Mock

from bs4 import BeautifulSoup

from gdt_tax.dvc_notices import parse_notice_list
from gdt_tax.gnt.parsing import gnt_page_count
from gdt_tax.legacy_notices import parse_legacy_notice_list
from gdt_tax.portals.dvc import DvcPortal
from gdt_tax.portals.etax import EtaxPortal
from gdt_tax.table_contracts import SCHEMAS
from gdt_tax.tb.parsing import tb_page_count
from tests.support import FakeHttp, FakeResponse, fixture
from tests.test_table_contracts import CASES, named_soup, read


class SchemaReviewTests(unittest.TestCase):
    def test_all_named_sources_accept_header_cell_markup_without_changing_fields(self):
        for source in CASES:
            for mutation in ('td_headings', 'no_thead', 'line_breaks'):
                with self.subTest(source=source, mutation=mutation):
                    soup = named_soup(source)
                    baseline = [row.to_dict() for row in read(source, str(soup)).records]
                    if mutation == 'td_headings':
                        for cell in soup.select('thead th'):
                            cell.name = 'td'
                    elif mutation == 'no_thead':
                        for cell in soup.select('thead td'):
                            cell.name = 'th'
                        soup.find('thead').unwrap()
                    else:
                        for cell in soup.select('thead th, thead td'):
                            text = cell.get_text(' ', strip=True)
                            cell.clear()
                            for part in text.split():
                                cell.append(part)
                                cell.append(soup.new_tag('br'))
                    parsed = read(source, str(soup))
                    self.assertEqual(parsed.diagnostics.status, 'PARSED')
                    self.assertEqual([row.to_dict() for row in parsed.records], baseline)

    def test_etax_repeated_css_containers_find_the_single_business_table(self):
        soup = named_soup('ETAX')
        baseline = [row.to_dict() for row in read('ETAX', str(soup)).records]
        empty = soup.new_tag('div', attrs={'class': 'bangKetQuaTraCuu_tdt'})
        soup.body.insert(0, empty)
        # Same real table reached through nested matching containers is one table.
        wrapper = soup.new_tag('div', attrs={'class': 'bangKetQuaTraCuu_tdt'})
        soup.select('.bangKetQuaTraCuu_tdt')[-1].wrap(wrapper)
        parsed = read('ETAX', str(soup))
        self.assertEqual(parsed.diagnostics.status, 'PARSED')
        self.assertEqual([row.to_dict() for row in parsed.records], baseline)

    def test_result_scope_may_be_the_table_itself(self):
        for source in ('ETAX', 'DVC'):
            with self.subTest(source=source):
                soup = named_soup(source)
                baseline = [row.to_dict() for row in read(source, str(soup)).records]
                scope = soup.select_one(SCHEMAS[source].container)
                table = scope.find('table')
                if source == 'DVC':
                    table['id'] = 'table-container'
                    del scope['id']
                else:
                    table['class'] = ['bangKetQuaTraCuu_tdt']
                    del scope['class']
                parsed = read(source, str(soup))
                self.assertEqual(parsed.diagnostics.status, 'PARSED')
                self.assertEqual([row.to_dict() for row in parsed.records], baseline)

    def test_two_real_tables_in_matching_containers_remain_ambiguous(self):
        soup = named_soup('ETAX')
        other = BeautifulSoup(fixture(CASES['ETAX']), 'lxml').select_one('.bangKetQuaTraCuu_tdt')
        soup.body.append(other)
        parsed = read('ETAX', str(soup))
        self.assertEqual(parsed.diagnostics.status, 'SCHEMA_CHANGED')
        self.assertEqual(parsed.records, [])

    def test_hidden_empty_messages_do_not_confirm_empty_results_on_any_source(self):
        for source in CASES:
            for hidden in ('hidden', 'style="display:none"', 'aria-hidden="true"'):
                with self.subTest(source=source, hidden=hidden):
                    soup = named_soup(source)
                    for row in list(soup.select('tbody tr')):
                        row.decompose()
                    if source == 'ETAX_LEGACY':
                        for row in list(soup.find('table').find_all('tr')):
                            if row.find_parent('thead') is None:
                                row.decompose()
                    marker = SCHEMAS[source].empty_markers[0]
                    scope = soup.select_one(SCHEMAS[source].container) if SCHEMAS[source].container else soup.body
                    element = BeautifulSoup(f'<div {hidden}><span>{marker}</span></div>', 'lxml').find('div')
                    scope.append(element)
                    parsed = read(source, str(soup))
                    self.assertEqual(parsed.diagnostics.status, 'SCHEMA_CHANGED')

    def test_etax_visible_empty_message_can_be_in_the_second_container(self):
        html = '<div class="bangKetQuaTraCuu_tdt"></div><div class="bangKetQuaTraCuu_tdt">Không có dữ liệu</div>'
        self.assertEqual(read('ETAX', html).diagnostics.status, 'EMPTY_CONFIRMED')

    def test_modern_captcha_variants_and_layout_tables_use_captcha_retry(self):
        for portal_type in (DvcPortal, EtaxPortal):
            for response in (FakeResponse('<table><tr><td>Mã xác thực không chính xác</td></tr></table>'),
                             FakeResponse('<p>Mã xác nhận không chính xác</p>'),
                             FakeResponse(json_payload={'code': 'CAPTCHA_INVALID'})):
                with self.subTest(portal=portal_type.__name__, text=response.text[:30]):
                    solver = Mock()
                    portal = portal_type(FakeHttp(lambda *_: None), solver, Mock(header_profile='minimal'))
                    result = portal._page_result(response)
                    self.assertEqual(result.diagnostics.status, 'CAPTCHA_INVALID')
                    solver.rejected.assert_called_once()
                    solver.accepted.assert_not_called()
            solver = Mock()
            portal = portal_type(FakeHttp(lambda *_: None), solver, Mock(header_profile='minimal'))
            response = FakeResponse('<div hidden><span>Mã xác thực không chính xác</span></div>')
            self.assertEqual(portal._page_result(response).diagnostics.status, 'SCHEMA_CHANGED')
            solver.rejected.assert_not_called()

    def test_legacy_notice_columns_are_read_by_name_with_td_or_reordered_headers(self):
        original = fixture('etax_legacy_notices.html')
        baseline = parse_legacy_notice_list(original).notices
        for mutation in ('reverse', 'td_headings', 'extra'):
            with self.subTest(mutation=mutation):
                soup = BeautifulSoup(original, 'lxml')
                for row in soup.find('table').find_all('tr'):
                    cells = row.find_all(['td', 'th'], recursive=False)
                    if mutation == 'reverse':
                        for cell in reversed(cells):
                            row.append(cell.extract())
                    elif mutation == 'td_headings':
                        for cell in cells:
                            cell.name = 'td'
                    else:
                        extra = soup.new_tag('th' if row.find_parent('thead') else 'td')
                        extra.string = 'Synthetic extra'
                        row.insert(2, extra)
                parsed = parse_legacy_notice_list(str(soup))
                self.assertEqual(parsed.status, 'PARSED')
                self.assertEqual(parsed.notices, baseline)

    def test_legacy_notice_duplicate_headers_and_data_spans_still_fail(self):
        for mutation in ('duplicate', 'span'):
            soup = BeautifulSoup(fixture('etax_legacy_notices.html'), 'lxml')
            if mutation == 'duplicate':
                soup.select('thead th')[-1].string = 'Ngày gửi'
            else:
                soup.select_one('tbody td')['colspan'] = '2'
            self.assertEqual(parse_legacy_notice_list(str(soup)).status, 'SCHEMA_UNKNOWN')

    def test_hidden_pagination_does_not_override_gnt_or_tb_page_count(self):
        for reader, name in ((gnt_page_count, 'gnt_results_page1.html'), (tb_page_count, 'tb_results_page1.html')):
            with self.subTest(name=name):
                html = fixture(name).replace('<body>', '<body><div hidden><span>Trang 1/999</span></div>')
                self.assertEqual(reader(html), 2)

    def test_hidden_notice_empty_placeholder_does_not_conflict_with_real_notices(self):
        html = ('<div id="modalThongBao" style="display:none"><div hidden>Không có thông báo</div>'
                '<a data-id="SYNTHETIC-1" onclick="downloadThongBao(this)">Download</a></div>')
        self.assertEqual(parse_notice_list(html).status, 'PARSED')
        empty = '<div id="modalThongBao" style="display:none">Không có thông báo</div>'
        self.assertEqual(parse_notice_list(empty).status, 'EMPTY_CONFIRMED')

    def test_gnt_conflicting_detail_and_download_ids_are_not_silently_accepted(self):
        html = fixture('gnt_results_page1.html').replace('chiTietCT(900000001)', 'chiTietCT(900000099)')
        parsed = read('GNT', html)
        self.assertEqual(parsed.diagnostics.status, 'SCHEMA_CHANGED')
        self.assertEqual(len(parsed.records), 1)
