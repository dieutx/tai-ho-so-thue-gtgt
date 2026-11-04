"""Test nguồn Thuế điện tử cũ, hoàn toàn offline qua ``FakeHttp``."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs

from bs4 import BeautifulSoup

from gdt_tax.config import Settings
from gdt_tax.constants import SOURCE_ETAX, SOURCE_ETAX_LEGACY
from gdt_tax.errors import LegacyEtaxError, LegacyPermissionError
from gdt_tax.models import CaseRecord, PageResult, SearchPeriod
from gdt_tax.parsing import parse_records
from gdt_tax.pipeline import Pipeline
from gdt_tax.portals.etax_legacy import (
    EtaxLegacyFallback,
    EtaxLegacyPortal,
)
from gdt_tax.storage import decode_zip_bytes
from tests.support import (
    FAKE_CAPTCHA_BYTES,
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    cleanup_temporary_directory,
    fixture,
    sample_zip,
)

IMAGE_HEADERS = {"content-type": "image/png"}
XML_BODY = b"<?xml version='1.0'?><HSoThueDTu>test</HSoThueDTu>"
NOTICE_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<TBaoThueDTu><MaTB>11200000034293775</MaTB></TBaoThueDTu>'
)

# --- Trang HTML giả lập từng bước đăng nhập trang legacy ---
FORM_HTML = "<html><form id='goProcForm' action='/etaxnnt/Request'><input name='x' value='1'></form></html>"
ESTABLISH_HTML = (
    "<script>window.location.href='/etaxnnt/Request?dse_sessionId=SESS01"
    "&dse_operationName=corpIndexProc'</script>"
)
LOGIN_OPTIONS_HTML = (
    FORM_HTML
    + "<script>window.location.href='/etaxnnt/Request?dse_sessionId=SESS01"
    + "&dse_nextEventName=login'</script></html>"
).replace("</form></html>", "</form>")  # FORM_HTML đã đóng html
LOGIN_PAGE_HTML = (
    "<html><form id='loginForm' action='/etaxnnt/Request'>"
    "<input name='dse_sessionId' value='SESS01'>"
    "<input name='isEtaxtmdt' value=''></form></html>"
)
LOGIN_OK_HTML = (
    "<html><form id='goProcForm' action='/etaxnnt/Request'><input name='x' value='1'></form>"
    "<script>window.location.href='/etaxnnt/Request?dse_sessionId=SESS01"
    "&dse_operationName=corporateHomeProc'</script></html>"
)
CORP_HOME_HTML = (
    "<html><script>var u='/etaxnnt/Request?dse_sessionId=SESS01&dse_pageId=7"
    "&dse_operationName=corpHomePageProc&dse_processorState=initial"
    "&dse_nextEventName=start';</script></html>"
)
SEARCH_START_HTML = (
    "<html><form id='traCuuKhaiForm' action='/etaxnnt/Request'>"
    "<input name='dse_sessionId' value='SESS01'>"
    "<input name='dse_applicationId' value='-1'>"
    "<input name='dse_pageId' value='7'>"
    "<input name='dse_processorState' value='viewTraCuuTkhai'>"
    "<input name='dse_processorId' value='PROCID01'>"
    "</form></html>"
)


def make_legacy_handler(state: dict):
    """Handler ``FakeHttp`` cho toàn bộ luồng legacy, định tuyến theo path + query."""

    def handler(method, path, kwargs):
        route = path.split("?", 1)[0]
        params: dict = dict(kwargs.get("params") or {})
        if "?" in path:
            for key, values in parse_qs(path.split("?", 1)[1]).items():
                params.setdefault(key, values[0])

        if method == "GET":
            if route == "/etaxnnt/EstablishSession":
                return FakeResponse(
                    ESTABLISH_HTML, url="https://thuedientu.gdt.gov.vn/etaxnnt/EstablishSession"
                )
            if route == "/etaxnnt/servlet/ImageServlet":
                return FakeResponse(content=FAKE_CAPTCHA_BYTES, headers=IMAGE_HEADERS)
            if route == "/etaxnnt/Request":
                operation = str(params.get("dse_operationName", ""))
                event = str(params.get("dse_nextEventName", ""))
                if operation == "corpHomePageProc":
                    return FakeResponse(
                        "<html></html>", url="https://thuedientu.gdt.gov.vn/etaxnnt/Request"
                    )
                if event == "login":
                    return FakeResponse(
                        LOGIN_PAGE_HTML, url="https://thuedientu.gdt.gov.vn/etaxnnt/Request"
                    )
                if operation == "corpIndexProc":
                    return FakeResponse(
                        FORM_HTML, url="https://thuedientu.gdt.gov.vn/etaxnnt/Request"
                    )
                if operation == "traCuuToKhaiProc" and event == "start":
                    return FakeResponse(
                        state.get("search_start_html", SEARCH_START_HTML),
                        url="https://thuedientu.gdt.gov.vn/etaxnnt/Request",
                    )
                if event == "downTkhai":
                    return state.get(
                        "download_response",
                        FakeResponse(
                            content=XML_BODY,
                            headers={"content-type": "application/octet-stream"},
                        ),
                    )
                if event == "viewTBao":
                    state.setdefault("notice_views", []).append(dict(params))
                    return FakeResponse(
                        state.get("notice_html", fixture("etax_legacy_notices.html")),
                        url="https://thuedientu.gdt.gov.vn/etaxnnt/Request",
                    )
        elif method == "POST":
            data = kwargs.get("data") or {}
            event = str(data.get("dse_nextEventName", ""))
            operation = str(data.get("dse_operationName", ""))
            url = "https://thuedientu.gdt.gov.vn/etaxnnt/Request"
            if event == "home":
                return FakeResponse(FORM_HTML, url=url)
            if event == "loginOptions":
                return FakeResponse(LOGIN_OPTIONS_HTML, url=url)
            if event == "start" and operation == "corporateHomeProc":
                return FakeResponse(CORP_HOME_HTML, url=url)
            if event == "start" and operation == "corpUserLoginProc":
                state["login_posts"] = state.get("login_posts", 0) + 1
                if state.get("accept_login", True):
                    return FakeResponse(LOGIN_OK_HTML, url=url)
                return FakeResponse(
                    "<html><form id='loginForm'></form><div>CAPTCHA không đúng</div><script>alert('Sai mat khau')</script></html>",
                    url=url,
                )
            if event == "download" and data.get("dse_processorState") == "dsTBaoViewPage":
                state["notice_downloads"] = state.get("notice_downloads", []) + [dict(data)]
                return FakeResponse(
                    content=NOTICE_XML,
                    headers={"content-type": "application/octet-stream"},
                )
            if event == "query":
                state["queries"] = state.get("queries", []) + [dict(data)]
                html = state.get("query_html", fixture("etax_legacy_results.html"))
                if data.get('ma_gd'):
                    soup = BeautifulSoup(html, 'lxml')
                    table = soup.find('table', id='data_content_onday')
                    if table:
                        for row in table.find_all('tr'):
                            cells = row.find_all('td', recursive=False)
                            if len(cells) > 1 and cells[1].get_text(strip=True) != data['ma_gd']:
                                row.decompose()
                        html = str(soup) if parse_records(str(soup), SOURCE_ETAX_LEGACY) else fixture('etax_legacy_empty.html')
                return FakeResponse(html, url=url)
        # Ghi lại request không khớp route để dễ chẩn đoán khi thêm endpoint mới.
        state.setdefault("unmatched", []).append((method, route, str(kwargs)[:200]))
        return FakeResponse("<html></html>", status_code=404)

    return handler


class LegacyParsingTests(unittest.TestCase):
    def test_doc_du_2_ho_so_tu_bang_legacy(self):
        records = parse_records(fixture("etax_legacy_results.html"), SOURCE_ETAX_LEGACY)
        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first.ma_ho_so, "11320200101110001")
        self.assertEqual(first.nguon, SOURCE_ETAX_LEGACY)
        self.assertEqual(first.ky_tinh_thue, "01/2020")
        self.assertEqual(first.loai_to_khai, "Chính thức")
        self.assertIn("GTGT", first.to_khai)
        self.assertEqual(first.noi_nop, "Thuế cơ sở 1 tỉnh Hà Tĩnh")

    def test_bo_qua_hang_khong_co_link_tai(self):
        records = parse_records(fixture("etax_legacy_empty.html"), SOURCE_ETAX_LEGACY)
        self.assertEqual(records, [])

    def test_nguon_la_khong_hop_le_thi_bao_loi(self):
        with self.assertRaises(ValueError):
            parse_records(fixture("etax_legacy_results.html"), "khong-ton-tai")


class LegacyPortalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state: dict = {}
        self.settings = Settings(
            username="synthetic-taxpayer-QL",
            password="mat-khau",
            from_date=date(2020, 1, 1),
            to_date=date(2020, 2, 29),
            download_dir=Path(self._tmp.name),
            login_attempts=2,
            search_attempts=1,
            pause_between_records=0.0,
            pause_between_pages=0.0,
        )

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def make_portal(self, state: dict | None = None) -> EtaxLegacyPortal:
        self.state = state if state is not None else {}
        http = FakeHttp(make_legacy_handler(self.state))
        return EtaxLegacyPortal(http, StubCaptcha(), self.settings, login_attempts=2)

    def period(self, **overrides) -> SearchPeriod:
        values = dict(start=date(2020, 1, 1), end=date(2020, 1, 31), source=SOURCE_ETAX_LEGACY)
        values.update(overrides)
        return SearchPeriod(**values)

    def test_login_va_search_tra_ve_ho_so(self):
        portal = self.make_portal()
        result = portal.search(self.period(), page=1)
        self.assertTrue(portal._logged_in)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.total_pages, 1)
        queries = self.state.get("queries", [])
        self.assertEqual(len(queries), 1)
        self.assertEqual(queries[0]["qryFromDate"], "01/01/2020")
        self.assertEqual(queries[0]["qryToDate"], "31/01/2020")

    def test_trang_chua_phan_quyen_bao_dung_ma_loi(self):
        # Cổng trả HTTP 200 kèm trang từ chối quyền: phải báo đúng là thiếu quyền,
        # không phải "cấu trúc trang chưa nhận diện" (gọi lại cũng không sửa được).
        denied = (
            "<html><body><div class='succeed_table_content'>"
            "<strong>Lỗi truy cập</strong><br/>"
            "<span>Bạn chưa được phân quyền sử dụng chức năng này!</span>"
            "</div></body></html>"
        )
        portal = self.make_portal({"search_start_html": denied})
        with self.assertRaises(LegacyPermissionError) as caught:
            portal.search(self.period(), page=1)
        self.assertEqual(caught.exception.code, "AUTH_FUNCTION_NOT_PERMITTED")
        self.assertIn("chưa được phân quyền", str(caught.exception))
        self.assertNotIn("SCHEMA_UNKNOWN", str(caught.exception))

    def test_search_lan_2_khong_dang_nhap_lai(self):
        portal = self.make_portal()
        portal.search(self.period(), page=1)
        portal.search(self.period(start=date(2020, 2, 1), end=date(2020, 2, 29)), page=1)
        establish_calls = [p for p in portal.http.paths("GET") if "EstablishSession" in p]
        self.assertEqual(len(establish_calls), 1)
        self.assertEqual(len(self.state.get("queries", [])), 2)

    def test_login_thu_lai_khi_sai_captcha(self):
        state = {"accept_login": False}
        portal = self.make_portal(state)
        with self.assertRaises(LegacyEtaxError):
            portal.search(self.period(), page=1)
        # login_attempts=2 → gửi form đăng nhập đúng 2 lần
        self.assertEqual(state["login_posts"], 2)

    def test_login_retry_uses_refreshed_hidden_fields_and_referer(self):
        portal = self.make_portal()
        initial = FakeResponse(LOGIN_PAGE_HTML.replace('</form>', "<input name='dse_pageId' value='old'></form>"),
                               url='https://fixture.test/initial')
        refreshed = FakeResponse(initial.text.replace("value='old'", "value='new'") + '<div>CAPTCHA không đúng</div>',
                                 url='https://fixture.test/retry')
        sent = []
        def post(action, fields, referer):
            sent.append((dict(fields), referer))
            if len(sent) == 1:
                return refreshed
            return FakeResponse(LOGIN_OK_HTML)
        with mock.patch.object(portal, '_legacy_captcha_image', return_value=FAKE_CAPTCHA_BYTES) as image, mock.patch.object(portal, '_post_fields', side_effect=post):
            portal._submit_login(initial)
        self.assertEqual([fields['dse_pageId'] for fields, _ in sent], ['old', 'new'])
        self.assertEqual([referer for _, referer in sent], [initial.url, refreshed.url])
        self.assertEqual(image.call_args_list, [mock.call(initial.url), mock.call(refreshed.url)])

    def test_renamed_tax_result_form_supports_next_query_and_download(self):
        portal = self.make_portal()
        renamed = fixture('etax_legacy_results.html').replace('traCuuKhaiForm', 'taxLookupForm')
        renamed = renamed.replace('</form>', "<input name='dse_operationName' value='traCuuToKhaiProc'></form>")
        self.state['query_html'] = renamed
        first = portal.search(self.period(), 1)
        self.assertEqual(len(first.records), 2)
        self.assertEqual(portal._search_form_id, 'taxLookupForm')
        self.assertEqual(len(portal.search(self.period(), 1).records), 2)
        self.assertIsNotNone(decode_zip_bytes(portal.download(first.records[0], '', '')))

    def test_expected_form_name_in_script_does_not_override_real_form(self):
        portal = self.make_portal()
        html = ("<script>var formName='traCuuKhaiForm';</script>"
                "<form id='taxLookupForm'><input name='dse_operationName' value='traCuuToKhaiProc'></form>")
        self.assertEqual(portal._form_id_for_operation(html, 'traCuuToKhaiProc', 'traCuuKhaiForm'), 'taxLookupForm')

    def test_tra_cuu_truoc_2015_khong_bi_chan_boi_moc_ngay(self):
        portal = self.make_portal({"query_html": fixture("etax_legacy_empty.html")})
        result = portal.search(
            self.period(start=date(2013, 1, 1), end=date(2013, 1, 31)), page=1
        )
        self.assertEqual(result.records, [])
        self.assertEqual(result.total_pages, 0)
        self.assertEqual(self.state["queries"][0]["qryFromDate"], "01/01/2013")
        self.assertEqual(self.state["queries"][0]["qryToDate"], "31/01/2013")

    def test_ho_so_cu_tra_thang_zip_van_luu_duoc(self):
        archive = sample_zip(b"<HSoThueDTu>old</HSoThueDTu>")
        portal = self.make_portal({
            "download_response": FakeResponse(
                content=archive, headers={"content-type": "application/octet-stream"}
            )
        })
        record = portal.search(self.period(), page=1).records[0]
        response = portal.download(record, "", "")
        self.assertEqual(decode_zip_bytes(response), archive)

    def test_mo_danh_sach_va_tai_thong_bao_dinh_kem(self):
        portal = self.make_portal()
        record = portal.search(self.period(), page=1).records[0]
        portal.fetch_detail_csrf(record)
        notices = portal.fetch_notices()
        self.assertEqual([notice.id for notice in notices],
                         ["11200000034293775", "11200000034284609"])
        self.assertEqual(notices[0].title,
                         "Chấp nhận/Không chấp nhận về việc nộp hồ sơ khai thuế điện tử")
        self.assertEqual(notices[0].sent_at, "20/01/2020 14:59:28")
        views = self.state["notice_views"]
        self.assertEqual(views[0]["ctMaGDich"], "11320200101119001")
        self.assertEqual(views[0]["dse_nextEventName"], "viewTBao")

        payload = portal.download_notice(notices[0], "", "")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.data, NOTICE_XML)
        posts = self.state["notice_downloads"]
        self.assertEqual(posts[0]["messageId"], "11200000034293775")
        self.assertEqual(posts[0]["dse_processorState"], "dsTBaoViewPage")

    def test_view_tbao_tra_lai_trang_tra_cuu_la_khong_co_dinh_kem(self):
        portal = self.make_portal({
            "notice_html": (
                "<html><title>Tra cứu tờ khai</title>"
                "<form id='tkhaiForm' action='/etaxnnt/Request'>"
                "<input name='dse_operationName' value='traCuuToKhaiProc'>"
                "</form><div>Tra cứu tờ khai</div></html>"
            )
        })
        record = portal.search(self.period(), page=1).records[0]
        portal.fetch_detail_csrf(record)
        listing = portal.fetch_notice_list()
        self.assertEqual(listing.notices, [])
        self.assertEqual(listing.status, "EMPTY_CONFIRMED")

    def test_notice_discovery_failure_clears_previous_form(self):
        portal = self.make_portal()
        record = portal.search(self.period(), page=1).records[0]
        portal.fetch_detail_csrf(record)
        self.assertEqual(portal.fetch_notice_list().status, 'PARSED')
        self.state['notice_html'] = '<html>unknown response</html>'
        self.assertEqual(portal.fetch_notice_list().status, 'SCHEMA_UNKNOWN')
        self.assertEqual(portal._notice_page_html, '')
        from gdt_tax.dvc_notices import DvcNotice
        self.assertIsNone(portal.download_notice(DvcNotice('123'), '', ''))

    def test_notice_download_uses_navigation_headers_and_legacy_identity(self):
        portal = self.make_portal()
        record = portal.search(self.period(), page=1).records[0]
        portal.fetch_detail_csrf(record)
        notice = portal.fetch_notice_list().notices[0]
        portal.download_notice(notice, '', '')
        headers = portal.http.calls[-1].kwargs['headers']
        self.assertNotIn('X-Requested-With', headers)
        self.assertEqual(notice.key(record.key).source, 'legacy')

    def test_tai_xml_duoc_goi_zip_hop_le(self):
        portal = self.make_portal()
        record = portal.search(self.period(), page=1).records[0]
        detail_url, csrf = portal.fetch_detail_csrf(record)
        self.assertEqual(csrf, "")  # legacy không dùng CSRF

        response = portal.download(record, detail_url, csrf)
        self.assertEqual(response.media_kind, 'zip')
        data = decode_zip_bytes(response)
        self.assertIsNotNone(data)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = archive.namelist()
        self.assertEqual(names, [f"{record.ma_ho_so}.xml"])
        self.assertIn(b"HSoThueDTu", data)

    def test_legacy_tra_html_thay_file_thi_khong_luu_nham(self):
        state = {
            "download_response": FakeResponse(
                "<html>Phiên hết hạn</html>", headers={"content-type": "text/html"}
            )
        }
        portal = self.make_portal(state)
        portal._search_page_html = SEARCH_START_HTML
        portal._search_page_url = "https://thuedientu.gdt.gov.vn/etaxnnt/Request"
        record = parse_records(fixture("etax_legacy_results.html"), SOURCE_ETAX_LEGACY)[0]
        response = portal.download(record, "https://x", "")
        self.assertIsNone(decode_zip_bytes(response))

    def test_xml_cu_co_doctype_nhung_khong_entity_van_nhan(self):
        body = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<!DOCTYPE HSoThueDTu SYSTEM "HSoThueDTu.dtd">'
            b"<HSoThueDTu>old</HSoThueDTu>"
        )
        portal = self.make_portal({"download_response": FakeResponse(
            content=body, headers={"content-type": "application/octet-stream"})})
        record = portal.search(self.period(), page=1).records[0]
        self.assertIsNotNone(decode_zip_bytes(portal.download(record, "", "")))

    def test_html_mime_sai_va_xml_hong_khong_duoc_goi_zip(self):
        for body in (b"<html><body>expired</body></html>", b"error", b"<HSoThueDTu>",
                     b'<!DOCTYPE x [<!ENTITY a "secret">]><x>&a;</x>'):
            with self.subTest(body=body):
                portal = self.make_portal({"download_response": FakeResponse(
                    content=body, headers={"content-type": "application/octet-stream"})})
                record = portal.search(self.period(), page=1).records[0]
                self.assertIsNone(decode_zip_bytes(portal.download(record, "", "")))

    def test_trang_loi_khong_ghi_de_form_tra_cuu_dang_co(self):
        portal = self.make_portal()
        portal.search(self.period(), 1)
        form = portal._search_page_html
        self.state["query_html"] = "<html>expired</html>"
        result = portal.search(self.period(), 2)
        self.assertIsNone(result.total_pages)
        self.assertEqual(portal._search_page_html, form)


class LegacyFallbackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(
            username="u",
            password="p",
            from_date=date(2020, 1, 1),
            to_date=date(2026, 9, 25),
            download_dir=Path(self._tmp.name),
            etax_cutoff=date(2025, 7, 1),
        )

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def make_fallback(self):
        primary = mock.Mock()
        primary.settings = self.settings
        legacy = mock.Mock()
        return EtaxLegacyFallback(primary, legacy), primary, legacy

    def test_search_uy_thac_cho_portal_goc(self):
        period = SearchPeriod(start=date(2020, 1, 1), end=date(2020, 1, 31), source=SOURCE_ETAX)
        fallback, primary, legacy = self.make_fallback()
        primary.search.return_value = PageResult()
        fallback.search(period, 1)
        primary.search.assert_called_once_with(period, 1)
        legacy.search.assert_not_called()

    def test_tai_ho_so_theo_nguon_cua_ho_so(self):
        fallback, primary, legacy = self.make_fallback()
        legacy_record = CaseRecord(ma_ho_so="11320200101110001", nguon=SOURCE_ETAX_LEGACY)
        fallback.fetch_detail_csrf(legacy_record)
        legacy.fetch_detail_csrf.assert_called_once_with(legacy_record)

        other_record = CaseRecord(ma_ho_so="X", nguon=SOURCE_ETAX)
        fallback.fetch_detail_csrf(other_record)
        primary.fetch_detail_csrf.assert_called_once_with(other_record)

    def test_thong_bao_di_theo_nguon_cua_ho_so(self):
        fallback, primary, legacy = self.make_fallback()
        legacy.fetch_notices.return_value = ["legacy-notice"]
        primary.fetch_notices.return_value = ["dvc-notice"]

        legacy_record = CaseRecord(ma_ho_so="L", nguon=SOURCE_ETAX_LEGACY)
        fallback.fetch_detail_csrf(legacy_record)
        self.assertEqual(fallback.fetch_notices(), ["legacy-notice"])
        legacy.fetch_notices.assert_called_once_with()

        dvc_record = CaseRecord(ma_ho_so="D", nguon=SOURCE_ETAX)
        fallback.fetch_detail_csrf(dvc_record)
        self.assertEqual(fallback.fetch_notices(), ["dvc-notice"])
        primary.fetch_notices.assert_called_once_with()


class PipelineLegacyRoutingTests(unittest.TestCase):
    """Legacy là nguồn chính trước cutoff, không cần request DVC."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def run_pipeline(self, state=None, **overrides):
        values = dict(
            username="u", password="p",
            from_date=date(2020, 1, 1), to_date=date(2020, 3, 31),
            download_dir=self.directory, login_attempts=1, search_attempts=1,
            pause_between_records=0.0, pause_between_pages=0.0,
        )
        values.update(overrides)
        state = {} if state is None else state
        http = FakeHttp(make_legacy_handler(state))
        summary = Pipeline(Settings(**values), http, StubCaptcha(),
                           sleep=lambda _seconds: None).run()
        return summary, http, state

    def test_legacy_duoc_dung_ngay_tu_doan_dau(self):
        summary, http, state = self.run_pipeline()
        queries = state["queries"]
        self.assertEqual([(q["qryFromDate"], q["qryToDate"]) for q in queries], [
            ("01/01/2020", "31/01/2020"),
            ("01/02/2020", "02/03/2020"),
            ("03/03/2020", "31/03/2020"),
        ])
        self.assertTrue(all(path.startswith("/etaxnnt/") for path in http.paths()))
        self.assertEqual(state["login_posts"], 1)
        self.assertEqual(summary.downloaded, 2)
        self.assertTrue(summary.complete)

    def test_ket_qua_rong_la_hop_le_va_khong_thu_lai(self):
        summary, http, state = self.run_pipeline(
            {"query_html": fixture("etax_legacy_empty.html")})
        self.assertEqual(summary.expected, 0)
        self.assertTrue(summary.complete)
        self.assertEqual(len(state["queries"]), 3)
        self.assertTrue(all(path.startswith("/etaxnnt/") for path in http.paths()))

    def test_khoang_vat_cutoff_chi_tra_cuu_phan_legacy(self):
        summary, http, state = self.run_pipeline(
            from_date=date(2025, 6, 30), to_date=date(2025, 7, 2))
        self.assertEqual(summary.skipped_periods, 1)
        self.assertEqual(summary.periods, 1)
        self.assertFalse(summary.complete)
        self.assertEqual(state["queries"][0]["qryToDate"], "30/06/2025")
        self.assertTrue(all(path.startswith("/etaxnnt/") for path in http.paths()))

    def test_chi_sau_cutoff_khong_goi_mang_va_bao_chua_day_du(self):
        summary, http, state = self.run_pipeline(
            from_date=date(2025, 7, 1), to_date=date(2025, 7, 31))
        self.assertEqual(http.calls, [])
        self.assertEqual(state, {})
        self.assertEqual(summary.skipped_periods, 1)
        self.assertFalse(summary.complete)
        self.assertFalse(summary.search_complete)

    def test_dry_run_chi_sau_cutoff_khong_bao_thanh_cong(self):
        summary, http, _ = self.run_pipeline(
            from_date=date(2025, 7, 1), to_date=date(2025, 7, 31), dry_run=True)
        self.assertFalse(summary.search_complete)
        self.assertEqual(http.calls, [])

    def test_case_id_khong_tim_thay_duoc_ghi_nhan(self):
        summary, _, _ = self.run_pipeline(case_id="missing", dry_run=True)
        self.assertEqual(summary.discovered, 0)
        self.assertEqual(summary.expected, 1)
        self.assertFalse(summary.search_complete)

    def test_tai_thong_bao_dinh_kem_cho_tung_ho_so(self):
        summary, _http, state = self.run_pipeline()
        self.assertEqual(summary.downloaded, 2)
        self.assertEqual(len(state["notice_views"]), 2)
        self.assertEqual(len(state["notice_downloads"]), 4)
        self.assertTrue(summary.attachments_complete)
        self.assertEqual(summary.attachments_downloaded, 4)
        for case in ("11320200101110001", "11320200101110002"):
            folder = self.directory / "thong-bao-dinh-kem" / case
            names = sorted(path.name for path in folder.glob("*.xml"))
            self.assertEqual(len(names), 2, names)
            self.assertTrue(any("tiep-nhan" in name for name in names))

    def test_lan_hai_khong_tai_lai_thong_bao_da_co(self):
        self.run_pipeline()
        _summary, _http, state = self.run_pipeline()
        self.assertEqual(state.get("notice_downloads", []), [])

    def test_unknown_notice_page_keeps_primary_but_reports_incomplete(self):
        summary, _http, _state = self.run_pipeline({'notice_html': '<html>unknown</html>'})
        self.assertEqual(summary.downloaded, 2)
        self.assertFalse(summary.attachments_complete)
        self.assertEqual(summary.attachments_failed, 2)
        self.assertEqual(len(list(self.directory.glob('*.zip'))), 2)

    def test_trang_tra_cuu_khi_khong_co_thong_bao_khong_phai_loi(self):
        summary, _http, _state = self.run_pipeline({
            'notice_html': (
                "<html><title>Tra cứu tờ khai</title>"
                "<form id='tkhaiForm' action='/etaxnnt/Request'>"
                "<input name='dse_operationName' value='traCuuToKhaiProc'>"
                "</form><div>Tra cứu tờ khai</div></html>"
            ),
        })
        self.assertEqual(summary.downloaded, 2)
        self.assertTrue(summary.attachments_complete)
        self.assertEqual(summary.attachments_failed, 0)

    def test_partial_notice_table_keeps_valid_items_and_incomplete_status(self):
        html = fixture('etax_legacy_notices.html').replace("downloadFile('11200000034284609')", "changedDownload('11200000034284609')")
        summary, _http, state = self.run_pipeline({'notice_html': html})
        self.assertEqual(summary.downloaded, 2)
        self.assertFalse(summary.attachments_complete)
        self.assertEqual(summary.attachments_discovered, 2)
        self.assertEqual(len(state['notice_downloads']), 2)

    def test_khoang_truoc_2015_van_duoc_chia_doan_va_tra_cuu(self):
        summary, _http, state = self.run_pipeline(
            {"query_html": fixture("etax_legacy_empty.html")},
            from_date=date(2013, 1, 1), to_date=date(2013, 3, 31))
        self.assertEqual(summary.periods, 3)
        self.assertTrue(summary.complete)
        self.assertEqual(
            [(q["qryFromDate"], q["qryToDate"]) for q in state["queries"]],
            [("01/01/2013", "31/01/2013"), ("01/02/2013", "03/03/2013"),
             ("04/03/2013", "31/03/2013")],
        )

    def test_phan_loai_hai_nhom_tu_legacy(self):
        import json

        self.run_pipeline()
        groups = json.loads((self.directory / "phan_loai_ho_so.json").read_text(encoding="utf-8"))
        self.assertEqual(len(groups["groups"]["GTGT"]), 1)
        self.assertEqual(len(groups["groups"]["TNCN"]), 1)
        self.assertTrue(all(row["tep_zip"] for group in groups["groups"].values() for row in group))


if __name__ == "__main__":
    unittest.main()
