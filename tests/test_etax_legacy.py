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

from gdt_tax.config import Settings
from gdt_tax.constants import SOURCE_ETAX, SOURCE_ETAX_LEGACY
from gdt_tax.errors import LegacyEtaxError
from gdt_tax.models import CaseRecord, PageResult, SearchPeriod
from gdt_tax.parsing import parse_records
from gdt_tax.pipeline import Pipeline
from gdt_tax.portals.etax_legacy import (
    EtaxLegacyFallback,
    EtaxLegacyPortal,
)
from gdt_tax.storage import ZipStore, decode_zip_bytes
from tests.support import (
    FAKE_CAPTCHA_BYTES,
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    fixture,
)

IMAGE_HEADERS = {"content-type": "image/png"}
XML_BODY = b"<?xml version='1.0'?><HSoThueDTu>test</HSoThueDTu>"

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
                        SEARCH_START_HTML, url="https://thuedientu.gdt.gov.vn/etaxnnt/Request"
                    )
                if event == "downTkhai":
                    state["download_calls"] = state.get("download_calls", 0) + 1
                    if state.pop("expire_download_once", False):
                        return FakeResponse(
                            LOGIN_PAGE_HTML,
                            headers={"content-type": "text/html"},
                        )
                    return state.get(
                        "download_response",
                        FakeResponse(
                            content=XML_BODY,
                            headers={"content-type": "application/octet-stream"},
                        ),
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
                    "<html><form id='loginForm'></form><script>alert('Sai mat khau')</script></html>",
                    url=url,
                )
            if event == "query":
                state["queries"] = state.get("queries", []) + [dict(data)]
                if state.pop("expire_query_once", False):
                    return FakeResponse(LOGIN_PAGE_HTML, url=url)
                return FakeResponse(state.get("query_html", fixture("etax_legacy_results.html")), url=url)
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
            username="0101234567-QL",
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
        self._tmp.cleanup()

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

    def test_search_lan_2_khong_dang_nhap_lai(self):
        portal = self.make_portal()
        portal.search(self.period(), page=1)
        portal.search(self.period(start=date(2020, 2, 1), end=date(2020, 2, 29)), page=1)
        establish_calls = [p for p in portal.http.paths("GET") if "EstablishSession" in p]
        self.assertEqual(len(establish_calls), 1)
        self.assertEqual(len(self.state.get("queries", [])), 2)

    def test_search_tu_dang_nhap_lai_khi_phien_het_han(self):
        state = {"expire_query_once": True}
        portal = self.make_portal(state)

        result = portal.search(self.period(), page=1)

        self.assertEqual(len(result.records), 2)
        self.assertEqual(state["login_posts"], 2)
        self.assertEqual(len(state["queries"]), 2)

    def test_login_thu_lai_khi_sai_captcha(self):
        state = {"accept_login": False}
        portal = self.make_portal(state)
        with self.assertRaises(LegacyEtaxError):
            portal.search(self.period(), page=1)
        # login_attempts=2 → gửi form đăng nhập đúng 2 lần
        self.assertEqual(state["login_posts"], 2)

    def test_tai_xml_duoc_goi_zip_hop_le(self):
        portal = self.make_portal()
        record = portal.search(self.period(), page=1).records[0]
        detail_url, csrf = portal.fetch_detail_csrf(record)
        self.assertEqual(csrf, "")  # legacy không dùng CSRF

        response = portal.download(record, detail_url, csrf)
        self.assertEqual(response.status_code, 200)
        data = decode_zip_bytes(response)
        self.assertIsNotNone(data)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = archive.namelist()
        self.assertEqual(names, [f"{record.ma_ho_so}.xml"])
        self.assertIn(b"HSoThueDTu", data)

    def test_tai_tu_dang_nhap_lai_va_khoi_phuc_truy_van_khi_phien_het_han(self):
        state = {"expire_download_once": True}
        portal = self.make_portal(state)
        record = portal.search(self.period(), page=1).records[0]

        response = portal.download(record, "https://x", "")

        self.assertIsNotNone(decode_zip_bytes(response))
        self.assertEqual(state["download_calls"], 2)
        self.assertEqual(state["login_posts"], 2)
        self.assertEqual(len(state["queries"]), 2)

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
        self._tmp.cleanup()

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


class PipelineLegacySwitchTests(unittest.TestCase):
    """Trước cutoff dùng thẳng legacy; có thể tắt khi DVC đã đồng bộ dữ liệu."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.state: dict = {}

    def tearDown(self):
        self._tmp.cleanup()

    def settings_for(self, **overrides) -> Settings:
        values = dict(
            username="u",
            password="p",
            from_date=date(2020, 1, 1),
            to_date=date(2020, 3, 31),
            download_dir=self.directory,
            login_attempts=1,
            search_attempts=1,
            pause_between_records=0.0,
            pause_between_pages=0.0,
            etax_cutoff=date(2025, 7, 1),
            legacy_etax=True,
        )
        values.update(overrides)
        return Settings(**values)

    def make_handler(self, state: dict, etax_results: str | None = None):
        """Handler cổng ETAX (hiện hồ sơ nhưng tải ZIP trả 500) + legacy đầy đủ."""
        results = etax_results if etax_results is not None else fixture("etax_results.html")

        def handler(method, path, kwargs):
            route = path.split("?", 1)[0]
            if method == "POST" and route in ("/tchs/thuedientu", "/ho-so/search"):
                state.setdefault("dvc_queries", []).append(route)
                return FakeResponse(results)
            if method == "POST" and route == "/loginLDAP":
                return FakeResponse(json_payload={"status": "200"})
            if method == "GET" and route == "/login":
                return FakeResponse(
                    '<html><meta name="csrf-token" content="csrf"></html>'
                )
            if route in ("/login/getCaptcha", "/getCaptcha"):
                return FakeResponse(content=FAKE_CAPTCHA_BYTES, headers=IMAGE_HEADERS)
            if method == "GET" and route == "/tchs":
                return FakeResponse(
                    '<html><input type="hidden" name="_csrf" value="csrf"></html>'
                )
            if route.startswith("/tchs/files/detail/"):
                return FakeResponse(
                    '<html><input type="hidden" name="_csrf" value="csrf"></html>'
                )
            if route == "/tchs/downloadhoso-tdt":
                return FakeResponse(
                    json_payload={"error": "Không tìm thấy hồ sơ tương ứng!"},
                    status_code=500,
                )
            return make_legacy_handler(state)(method, path, kwargs)

        return handler

    def run_pipeline(self, state: dict):
        settings = self.settings_for()
        http = FakeHttp(self.make_handler(state))
        pipeline = Pipeline(
            settings,
            http,
            StubCaptcha(),
            store=ZipStore(settings.download_dir),
            sleep=lambda _seconds: None,
        )
        return pipeline.run(), state, settings

    def test_mac_dinh_quet_thang_legacy_cho_moi_doan_truoc_cutoff(self):
        state: dict = {}
        summary, state, settings = self.run_pipeline(state)
        queries = state.get("queries", [])
        self.assertTrue(queries)
        first = queries[0]
        self.assertEqual(first["qryFromDate"], "01/01/2020")
        self.assertEqual(first["qryToDate"], "31/01/2020")
        self.assertEqual(queries[1]["qryFromDate"], "01/02/2020")
        self.assertEqual(queries[1]["qryToDate"], "02/03/2020")
        self.assertEqual(queries[2]["qryToDate"], "31/03/2020")
        self.assertEqual(summary.periods, 3)
        self.assertEqual(state.get("dvc_queries", []), [])
        zips = list(self.directory.glob("*.zip"))
        self.assertTrue(zips)

    def test_tat_legacy_thi_tra_cuu_etax_tren_dvc(self):
        state: dict = {}
        settings = self.settings_for(legacy_etax=False)
        empty_results = (
            "<html><body>"
            "<input id='goToPage_tdt' min='1' max='1' type='number'>"
            "<table id='bangKetQuaTraCuu_tdt'><tbody></tbody></table>"
            "</body></html>"
        )
        http = FakeHttp(self.make_handler(state, etax_results=empty_results))
        pipeline = Pipeline(
            settings,
            http,
            StubCaptcha(),
            store=ZipStore(settings.download_dir),
            sleep=lambda _seconds: None,
        )
        pipeline.run()
        legacy_requests = [p for p in http.paths("POST") if "thuedientu.gdt" in p]
        self.assertEqual(legacy_requests, [])
        self.assertEqual(state["dvc_queries"], ["/tchs/thuedientu"] * 3)


if __name__ == "__main__":
    unittest.main()
