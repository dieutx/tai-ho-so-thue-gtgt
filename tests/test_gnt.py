"""Test luồng giấy nộp tiền (GNT), hoàn toàn offline qua ``FakeHttp``."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs

from openpyxl import load_workbook

from gdt_tax.config import Settings
from gdt_tax.constants import SOURCE_GNT
from gdt_tax.errors import LegacyEtaxError
from gdt_tax.gnt.models import gnt_periods
from gdt_tax.gnt.naming import gnt_xml_filename
from gdt_tax.gnt.parsing import gnt_page_count, parse_gnt_records
from gdt_tax.gnt.pipeline import GntPipeline
from gdt_tax.gnt.portal import GntPortal, is_gnt_xml
from gdt_tax.models import SearchPeriod
from tests.support import (
    FAKE_CAPTCHA_BYTES,
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    cleanup_temporary_directory,
    fixture,
)

IMAGE_HEADERS = {"content-type": "image/png"}
XML_HEADERS = {"content-type": "application/octet-stream"}
GNT_XML = fixture("gnt_chungtu.xml").encode("utf-8")

FORM_HTML = "<html><form id='goProcForm' action='/etaxnnt/Request'><input name='x' value='1'></form></html>"
ESTABLISH_HTML = (
    "<script>window.location.href='/etaxnnt/Request?dse_sessionId=SESS01"
    "&dse_operationName=corpIndexProc'</script>"
)
LOGIN_OPTIONS_HTML = (
    FORM_HTML
    + "<script>window.location.href='/etaxnnt/Request?dse_sessionId=SESS01"
    + "&dse_nextEventName=login'</script>"
)
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
GNT_START_HTML = (
    "<html><form id='reportForm' action='/etaxnnt/Request'>"
    "<input name='dse_sessionId' value='SESS01'>"
    "<input name='dse_applicationId' value='-1'>"
    "<input name='dse_pageId' value='7'>"
    "<input name='dse_processorState' value='initial'>"
    "<input name='dse_processorId' value='PROCID01'>"
    "<input type='checkbox' name='type_tax' value='01' checked='checked'>"
    "<input type='checkbox' name='type_tax' value='02'>"
    "</form></html>"
)
REQUEST_URL = "https://thuedientu.gdt.gov.vn/etaxnnt/Request"


def make_gnt_handler(state: dict):
    """Handler cho toàn bộ luồng đăng nhập legacy + tra cứu/tải GNT."""

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
                    return FakeResponse("<html></html>", url=REQUEST_URL)
                if operation == "corpQueryTaxProc" and event == "start":
                    return FakeResponse(GNT_START_HTML, url=REQUEST_URL)
                if event == "login":
                    return FakeResponse(LOGIN_PAGE_HTML, url=REQUEST_URL)
                if operation == "corpIndexProc":
                    return FakeResponse(FORM_HTML, url=REQUEST_URL)
        elif method == "POST":
            data = kwargs.get("data") or {}
            event = str(data.get("dse_nextEventName", ""))
            operation = str(data.get("dse_operationName", ""))
            if event == "home":
                return FakeResponse(FORM_HTML, url=REQUEST_URL)
            if event == "loginOptions":
                return FakeResponse(LOGIN_OPTIONS_HTML, url=REQUEST_URL)
            if event == "start" and operation == "corporateHomeProc":
                return FakeResponse(CORP_HOME_HTML, url=REQUEST_URL)
            if event == "start" and operation == "corpUserLoginProc":
                state["login_posts"] = state.get("login_posts", 0) + 1
                if state.get("accept_login", True):
                    return FakeResponse(LOGIN_OK_HTML, url=REQUEST_URL)
                return FakeResponse(
                    "<html><form id='loginForm'></form><script>alert('Sai')</script></html>",
                    url=REQUEST_URL,
                )
            if operation == "corpQueryTaxProc" and event == "query":
                state.setdefault("queries", []).append(dict(data))
                page_html = state.get("query_html") or (
                    fixture("gnt_results_page1.html")
                    if str(data.get("pn", "1")) == "1"
                    else fixture("gnt_results_page2.html")
                )
                if isinstance(page_html, dict):
                    page_html = page_html.get(str(data.get("pn", "1")), "")
                return FakeResponse(page_html, url=REQUEST_URL)
            if operation == "corpQueryTaxProc" and event == "download":
                state.setdefault("downloads", []).append(data.get("ctuId"))
                return state.get(
                    "download_response",
                    FakeResponse(content=GNT_XML, headers=XML_HEADERS),
                )
        state.setdefault("unmatched", []).append((method, route, str(kwargs)[:200]))
        return FakeResponse("<html></html>", status_code=404)

    return handler


class GntParsingTests(unittest.TestCase):
    def test_doc_hai_gnt_trang_1(self):
        records = parse_gnt_records(fixture("gnt_results_page1.html"))
        self.assertEqual([r.ctu_id for r in records], ["900000001", "900000002"])
        first = records[0]
        self.assertEqual(first.so_gnt, "000000101234567-01309202600000001")
        self.assertEqual(first.so_tien, "17,500")
        self.assertEqual(first.ngay_lap, "19/09/2026 14:52:44")
        self.assertEqual(first.trang_thai, "Nộp thuế thành công")
        self.assertEqual(first.ngan_hang, "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam")
        self.assertEqual(first.co_ds_chi_tiet_tncn, "Có")
        self.assertEqual(first.co_ds_chi_tiet_tmdt, "")
        self.assertEqual(records[1].co_ds_chi_tiet_tmdt, "Có")

    def test_doc_trang_2(self):
        records = parse_gnt_records(fixture("gnt_results_page2.html"))
        self.assertEqual([r.ctu_id for r in records], ["900000003"])
        self.assertEqual(records[0].so_tien, "1,000,000")

    def test_so_trang(self):
        self.assertEqual(gnt_page_count(fixture("gnt_results_page1.html")), 2)
        self.assertEqual(gnt_page_count(fixture("gnt_results_page2.html")), 2)
        self.assertEqual(gnt_page_count("<html></html>"), 0)

    def test_ten_file_xml_uu_tien_so_gnt(self):
        record = parse_gnt_records(fixture("gnt_results_page1.html"))[0]
        self.assertEqual(
            gnt_xml_filename(record),
            "000000101234567-01309202600000001__900000001.xml",
        )

    def test_ma_gnt_khong_tao_duong_dan_ngoai_output(self):
        record = parse_gnt_records(fixture("gnt_results_page1.html"))[0]
        record.so_gnt = ""
        for value in ("../../outside", r"..\..\outside", "C:/outside", "nested/name"):
            with self.subTest(value=value):
                record.ctu_id = value
                name = gnt_xml_filename(record)
                self.assertEqual(Path(name).name, name)
                self.assertNotIn("/", name)
                self.assertNotIn("\\", name)
                self.assertNotIn(":", name)


class GntPeriodsTests(unittest.TestCase):
    def test_chia_doan_31_ngay(self):
        periods = gnt_periods(date(2026, 1, 1), date(2026, 3, 15), 31)
        self.assertEqual([(p.start.isoformat(), p.end.isoformat()) for p in periods], [
            ("2026-01-01", "2026-01-31"),
            ("2026-02-01", "2026-03-03"),
            ("2026-03-04", "2026-03-15"),
        ])
        self.assertTrue(all(p.source == SOURCE_GNT for p in periods))


class GntPortalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state: dict = {}
        self.settings = Settings(
            username="synthetic-QL",
            password="mat-khau",
            from_date=date(2026, 9, 1),
            to_date=date(2026, 9, 30),
            download_dir=Path(self._tmp.name),
            login_attempts=2,
            search_attempts=1,
            pause_between_records=0.0,
            pause_between_pages=0.0,
        )

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def make_portal(self, state: dict | None = None) -> GntPortal:
        self.state = state if state is not None else {}
        http = FakeHttp(make_gnt_handler(self.state))
        return GntPortal(http, StubCaptcha(), self.settings, login_attempts=2)

    def period(self) -> SearchPeriod:
        return SearchPeriod(date(2026, 9, 1), date(2026, 9, 30), SOURCE_GNT)

    def test_tra_cuu_gnt_sau_dang_nhap(self):
        portal = self.make_portal()
        result = portal.search_gnt(self.period(), page=1)
        self.assertTrue(portal._logged_in)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.total_pages, 2)
        query = self.state["queries"][0]
        self.assertEqual(query["type_tax"], "01")
        self.assertEqual(query["ngay_lap_tu_ngay"], "01/09/2026")
        self.assertEqual(query["ngay_lap_den_ngay"], "30/09/2026")

    def test_tai_gnt_tra_ve_xml(self):
        portal = self.make_portal()
        record = portal.search_gnt(self.period(), 1).records[0]
        data = portal.download_gnt(record)
        self.assertIsNotNone(data)
        self.assertTrue(is_gnt_xml(data))
        self.assertEqual(self.state["downloads"], ["900000001"])

    def test_html_thay_xml_thi_khong_luu_nham(self):
        portal = self.make_portal(
            {"download_response": FakeResponse("<html>hết phiên</html>",
                                               headers={"content-type": "text/html"})}
        )
        record = portal.search_gnt(self.period(), 1).records[0]
        self.assertIsNone(portal.download_gnt(record))

    def test_trang_loi_khong_ghi_de_form_dang_co(self):
        portal = self.make_portal()
        portal.search_gnt(self.period(), 1)
        form = portal._search_page_html
        self.state["query_html"] = "<html>hết phiên</html>"
        result = portal.search_gnt(self.period(), 2)
        self.assertIsNone(result.total_pages)
        self.assertEqual(portal._search_page_html, form)

    def test_open_gnt_page_loi_khi_thieu_form(self):
        http = FakeHttp(lambda method, path, kwargs: FakeResponse("<html></html>"))
        portal = GntPortal(http, StubCaptcha(), self.settings, login_attempts=1)
        portal.dse_session_id = "SESS01"
        portal.home_page_id = "7"
        with self.assertRaises(LegacyEtaxError):
            portal._open_gnt_page()


class GntPipelineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def run_pipeline(self, state=None, **overrides):
        values = dict(
            username="u", password="p",
            from_date=date(2026, 9, 1), to_date=date(2026, 9, 30),
            download_dir=self.directory, login_attempts=1, search_attempts=1,
            pause_between_records=0.0, pause_between_pages=0.0,
        )
        values.update(overrides)
        state = {} if state is None else state
        http = FakeHttp(make_gnt_handler(state))
        summary = GntPipeline(Settings(**values), http, StubCaptcha(),
                              sleep=lambda _seconds: None).run()
        return summary, http, state

    def test_tai_het_xml_va_xuat_danh_muc(self):
        summary, http, state = self.run_pipeline()
        self.assertEqual(summary.discovered, 3)
        self.assertEqual(summary.downloaded, 3)
        self.assertTrue(summary.complete)
        xml_files = sorted(p.name for p in self.directory.glob("*.xml"))
        self.assertEqual(xml_files, [
            "000000101234567-01309202600000001__900000001.xml",
            "000000101234567-01609202600000002__900000002.xml",
            "000000101234567-01709202600000003__900000003.xml",
        ])
        self.assertTrue((self.directory / "danh_sach_giay_nop_tien.xlsx").exists())
        rows = json.loads((self.directory / "danh_sach_giay_nop_tien.json").read_text("utf-8"))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["tep_xml"] for row in rows))
        self.assertTrue(all(path.startswith("/etaxnnt/") for path in http.paths()))

    def test_excel_co_du_cot_va_ten_file(self):
        self.run_pipeline()
        workbook = load_workbook(self.directory / "danh_sach_giay_nop_tien.xlsx")
        sheet = workbook.active
        headers = [cell.value for cell in sheet[1]]
        self.assertIn("Số giấy nộp tiền", headers)
        self.assertIn("File XML", headers)
        self.assertEqual(sheet.max_row, 4)  # 1 tiêu đề + 3 GNT
        workbook.close()

    def test_chay_lai_khong_tai_lai_xml(self):
        self.run_pipeline()
        summary, _, state = self.run_pipeline()
        self.assertEqual(summary.downloaded, 3)
        self.assertFalse(state.get("downloads"))

    def test_tai_lai_thanh_cong_o_doan_sau_giu_ten_file_trong_metadata(self):
        with mock.patch.object(GntPortal, "download_gnt", side_effect=[None, GNT_XML, GNT_XML, GNT_XML]):
            summary, _, _ = self.run_pipeline(to_date=date(2026, 10, 31))
        self.assertTrue(summary.complete)
        rows = json.loads((self.directory / "danh_sach_giay_nop_tien.json").read_text("utf-8"))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["tep_xml"] and (self.directory / row["tep_xml"]).is_file() for row in rows))

    def test_dry_run_khong_tai(self):
        summary, _, state = self.run_pipeline(dry_run=True)
        self.assertEqual(summary.discovered, 3)
        self.assertEqual(summary.downloaded, 0)
        self.assertEqual(list(self.directory.glob("*.xml")), [])
        self.assertFalse(state.get("downloads"))

    def test_trang_lap_lai_thi_bao_loi(self):
        from gdt_tax.errors import SearchError

        state = {"query_html": fixture("gnt_results_page1.html")}
        # trang 2 trả lại đúng trang 1 → không xác nhận được đã tra cứu đủ
        with self.assertRaises(SearchError):
            self.run_pipeline(state)


if __name__ == "__main__":
    unittest.main()
