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
from gdt_tax.storage import decode_zip_bytes
from tests.support import (
    FAKE_CAPTCHA_BYTES,
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    cleanup_temporary_directory,
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

    def test_phan_loai_hai_nhom_tu_legacy(self):
        import json

        self.run_pipeline()
        groups = json.loads((self.directory / "phan_loai_ho_so.json").read_text(encoding="utf-8"))
        self.assertEqual(len(groups["groups"]["GTGT"]), 1)
        self.assertEqual(len(groups["groups"]["TNCN"]), 1)
        self.assertTrue(all(row["tep_zip"] for group in groups["groups"].values() for row in group))


if __name__ == "__main__":
    unittest.main()
