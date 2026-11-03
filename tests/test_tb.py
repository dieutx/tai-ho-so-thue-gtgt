"""Test luồng thông báo của cơ quan thuế (TB), hoàn toàn offline qua ``FakeHttp``."""

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
from gdt_tax.constants import SOURCE_TB
from gdt_tax.errors import LegacyEtaxError, SearchError
from gdt_tax.models import SearchPeriod
from gdt_tax.tb.models import tb_periods
from gdt_tax.tb.naming import tb_pdf_filename
from gdt_tax.tb.parsing import parse_tb_records, tb_page_count
from gdt_tax.tb.pipeline import TbPipeline
from gdt_tax.tb.portal import TbPortal, is_tb_pdf
from tests.support import (
    FAKE_CAPTCHA_BYTES,
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    cleanup_temporary_directory,
    fixture,
)

IMAGE_HEADERS = {"content-type": "image/png"}
PDF_HEADERS = {"content-type": "application/octet-stream"}
TB_PDF = (Path(__file__).parent / "fixtures" / "tb_notice.pdf").read_bytes()

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
    "<html><script>var u='/etaxnnt/Request?dse_sessionId=SESS01&dse_pageId=4"
    "&dse_operationName=corpHomePageProc&dse_processorState=initial"
    "&dse_nextEventName=start';</script></html>"
)
TB_START_HTML = (
    "<html><form name='' method='post' action='/etaxnnt/Request' id='tKhaiForm'>"
    "<input type='hidden' name='dse_sessionId' value='SESS01'>"
    "<input type='hidden' name='dse_applicationId' value='-1'>"
    "<input type='hidden' name='dse_operationName' value='tracuuTBThueKhacProc'>"
    "<input type='hidden' name='dse_pageId' value='5'>"
    "<input type='hidden' name='dse_processorState' value='queryTCTBTKhac'>"
    "<input type='hidden' name='dse_processorId' value='PROCID01'>"
    "<input type='hidden' name='messageId' id='messageId' value=''>"
    "<input type='hidden' name='ma_tbao' id='ma_tbao' value=''>"
    "<input type='hidden' name='pageNumber' value='1'>"
    "<input type='text' name='tuNgayNop' id='tuNgayNop' value=''>"
    "<input type='text' name='denNgayNop' id='denNgayNop' value=''>"
    "</form></html>"
)
REQUEST_URL = "https://thuedientu.gdt.gov.vn/etaxnnt/Request"


def make_tb_handler(state: dict):
    """Handler cho luồng đăng nhập legacy + tra cứu/tải thông báo."""

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
                if operation == "tracuuTBThueKhacProc" and event == "start":
                    if str(params.get("dse_pageId", "")) == "98":
                        return FakeResponse(state.get("redirected_html") or TB_START_HTML, url=REQUEST_URL)
                    if state.get("start_redirect"):
                        return FakeResponse(state["start_redirect"], url=REQUEST_URL)
                    return FakeResponse(state.get("start_html") or TB_START_HTML, url=REQUEST_URL)
                if operation == "tracuuTBThueKhacProc" and event == "query":
                    state.setdefault("paged", []).append(str(params.get("pn")))
                    page_html = state.get("paged_html", fixture("tb_results_page2.html"))
                    return FakeResponse(page_html, url=REQUEST_URL)
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
            if operation == "tracuuTBThueKhacProc" and event == "query":
                state.setdefault("queries", []).append(dict(data))
                page_html = state.get("query_html", fixture("tb_results_page1.html"))
                return FakeResponse(page_html, url=REQUEST_URL)
            if operation == "tracuuTBThueKhacProc" and event == "download":
                state.setdefault("downloads", []).append(data.get("messageId"))
                return state.get(
                    "download_response",
                    FakeResponse(content=TB_PDF, headers=PDF_HEADERS),
                )
        state.setdefault("unmatched", []).append((method, route, str(kwargs)[:200]))
        return FakeResponse("<html></html>", status_code=404)

    return handler


class TbParsingTests(unittest.TestCase):
    def test_doc_hai_thong_bao_trang_1(self):
        records = parse_tb_records(fixture("tb_results_page1.html"))
        self.assertEqual(
            [r.message_id for r in records],
            ["90000000000000001", "90000000000000002"],
        )
        first = records[0]
        self.assertEqual(first.ma_tbao, "608")
        self.assertEqual(first.ma_thong_bao, "01/TTN")
        self.assertEqual(first.so_thong_bao, "25799/TB-TCS1-KDT")
        self.assertEqual(first.ngay_gui, "10/08/2026 05:40:49")
        self.assertEqual(first.trang_thai, "Chưa xem")
        self.assertEqual(first.co_van_ban_giai_trinh, "")
        self.assertEqual(records[1].co_van_ban_giai_trinh, "Có")
        self.assertEqual(records[1].co_phan_hoi_ra_soat, "Có")

    def test_so_trang(self):
        self.assertEqual(tb_page_count(fixture("tb_results_page1.html")), 2)
        self.assertEqual(tb_page_count(fixture("tb_results_page2.html")), 2)
        self.assertEqual(tb_page_count("<html></html>"), 0)

    def test_ten_file_pdf(self):
        record = parse_tb_records(fixture("tb_results_page1.html"))[0]
        self.assertEqual(tb_pdf_filename(record), "25799-TB-TCS1-KDT__90000000000000001.pdf")


class TbPeriodsTests(unittest.TestCase):
    def test_chia_doan_31_ngay(self):
        periods = tb_periods(date(2026, 8, 1), date(2026, 9, 30), 31)
        self.assertEqual([(p.start.isoformat(), p.end.isoformat()) for p in periods], [
            ("2026-08-01", "2026-08-31"),
            ("2026-09-01", "2026-09-30"),
        ])
        self.assertTrue(all(p.source == SOURCE_TB for p in periods))


class TbPortalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state: dict = {}
        self.settings = Settings(
            username="synthetic-QL",
            password="mat-khau",
            from_date=date(2026, 8, 1),
            to_date=date(2026, 9, 30),
            download_dir=Path(self._tmp.name),
            login_attempts=2,
            search_attempts=1,
            pause_between_records=0.0,
            pause_between_pages=0.0,
        )

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def make_portal(self, state: dict | None = None) -> TbPortal:
        self.state = state if state is not None else {}
        http = FakeHttp(make_tb_handler(self.state))
        return TbPortal(http, StubCaptcha(), self.settings, login_attempts=2)

    def period(self) -> SearchPeriod:
        return SearchPeriod(date(2026, 8, 1), date(2026, 8, 31), SOURCE_TB)

    def test_tra_cuu_thong_bao_sau_dang_nhap(self):
        portal = self.make_portal()
        result = portal.search_tb(self.period(), page=1)
        self.assertTrue(portal._logged_in)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.total_pages, 2)
        query = self.state["queries"][0]
        self.assertEqual(query["tuNgayNop"], "01/08/2026")
        self.assertEqual(query["denNgayNop"], "31/08/2026")

    def test_trang_khong_co_ket_qua_la_empty_confirmed(self):
        empty_page = (
            TB_START_HTML.replace(
                "</form>",
                "<select name='loaiTB'><option value=''>--</option></select></form>",
            )
            + "<div>Không tìm thấy kết quả tra cứu.</div>"
        )
        portal = self.make_portal({"query_html": empty_page})
        result = portal.search_tb(self.period(), 1)
        self.assertEqual(result.records, [])
        self.assertEqual(result.total_pages, 1)
        self.assertEqual(result.diagnostics.status, "EMPTY_CONFIRMED")
        self.assertTrue(result.diagnostics.complete)

    def test_gui_gia_tri_select_loai_tb(self):
        page = TB_START_HTML.replace(
            "</form>",
            "<select name='loaiTB'><option value=''>--</option>"
            "<option value='911' selected>Thông báo</option></select></form>",
        )
        portal = self.make_portal({"start_html": page})
        portal.search_tb(self.period(), 1)
        self.assertEqual(self.state["queries"][0]["loaiTB"], "911")

    def test_phan_trang_bang_get(self):
        portal = self.make_portal()
        portal.search_tb(self.period(), 1)
        result = portal.search_tb(self.period(), 2)
        self.assertEqual([r.message_id for r in result.records], ["90000000000000003"])
        self.assertEqual(self.state["paged"], ["2"])

    def test_tai_thong_bao_tra_ve_pdf(self):
        portal = self.make_portal()
        record = portal.search_tb(self.period(), 1).records[0]
        data = portal.download_tb(record)
        self.assertIsNotNone(data)
        self.assertTrue(is_tb_pdf(data))
        self.assertEqual(self.state["downloads"], ["90000000000000001"])

    def test_download_uses_real_result_form_after_portal_renames_it(self):
        portal = self.make_portal({'query_html': fixture('tb_results_page1.html').replace('tKhaiForm', 'tbLookupForm')})
        record = portal.search_tb(self.period(), 1).records[0]
        self.assertEqual(portal._search_form_id, 'tbLookupForm')
        self.assertTrue(is_tb_pdf(portal.download_tb(record)))

    def test_html_thay_pdf_thi_khong_luu_nham(self):
        portal = self.make_portal(
            {"download_response": FakeResponse("<html>hết phiên</html>",
                                               headers={"content-type": "text/html"})}
        )
        record = portal.search_tb(self.period(), 1).records[0]
        self.assertIsNone(portal.download_tb(record))

    def test_trang_loi_khong_ghi_de_form_dang_co(self):
        portal = self.make_portal()
        portal.search_tb(self.period(), 1)
        form = portal._search_page_html
        self.state["query_html"] = "<html>hết phiên</html>"
        result = portal.search_tb(self.period(), 1)
        self.assertIsNone(result.total_pages)
        self.assertEqual(portal._search_page_html, form)

    def test_open_tb_page_loi_khi_thieu_form(self):
        http = FakeHttp(lambda method, path, kwargs: FakeResponse("<html></html>"))
        portal = TbPortal(http, StubCaptcha(), self.settings, login_attempts=1)
        portal.dse_session_id = "SESS01"
        portal.home_page_id = "4"
        with self.assertRaises(LegacyEtaxError) as caught:
            portal._open_tb_page()
        self.assertIn("thông báo", str(caught.exception))
        self.assertIn("HTTP 200", str(caught.exception))

    def test_open_tb_page_chap_nhan_form_id_khac(self):
        portal = self.make_portal({
            "start_html": (
                "<html><form id='tbLookupForm' action='/etaxnnt/Request'>"
                "<input name='dse_sessionId' value='SESS01'>"
                "<input name='dse_operationName' value='tracuuTBThueKhacProc'>"
                "<input name='dse_pageId' value='4'></form></html>"
            ),
        })
        portal.dse_session_id = "SESS01"
        portal.home_page_id = "4"
        portal._open_tb_page()
        self.assertEqual(portal._search_form_id, "tbLookupForm")
        result = portal.search_tb(self.period(), 1)
        self.assertEqual(len(result.records), 2)

    def test_open_tb_page_di_theo_chuyen_huong_js(self):
        redirect = (
            "<html><script>window.location.href='/etaxnnt/Request?dse_sessionId=SESS01"
            "&dse_pageId=98&dse_operationName=tracuuTBThueKhacProc"
            "&dse_processorState=initial&dse_nextEventName=start';</script></html>"
        )
        portal = self.make_portal({"start_redirect": redirect})
        result = portal.search_tb(self.period(), 1)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(portal._search_form_id, "tKhaiForm")


class TbPipelineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def run_pipeline(self, state=None, **overrides):
        values = dict(
            username="u", password="p",
            from_date=date(2026, 8, 1), to_date=date(2026, 9, 30),
            download_dir=self.directory, login_attempts=1, search_attempts=1,
            pause_between_records=0.0, pause_between_pages=0.0,
        )
        values.update(overrides)
        state = {} if state is None else state
        http = FakeHttp(make_tb_handler(state))
        summary = TbPipeline(Settings(**values), http, StubCaptcha(),
                             sleep=lambda _seconds: None).run()
        return summary, http, state

    def test_tai_het_pdf_va_xuat_danh_muc(self):
        summary, http, state = self.run_pipeline()
        self.assertEqual(summary.discovered, 3)
        self.assertEqual(summary.downloaded, 3)
        self.assertTrue(summary.complete)
        pdf_files = sorted(p.name for p in self.directory.glob("*.pdf"))
        self.assertEqual(pdf_files, [
            "153248-TB-TCS25-KDT__90000000000000003.pdf",
            "17884-QD-TCS25-KDT__90000000000000002.pdf",
            "25799-TB-TCS1-KDT__90000000000000001.pdf",
        ])
        self.assertTrue((self.directory / "danh_sach_thong_bao.xlsx").exists())
        rows = json.loads((self.directory / "danh_sach_thong_bao.json").read_text("utf-8"))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["tep_pdf"] for row in rows))
        self.assertTrue(all(path.startswith("/etaxnnt/") for path in http.paths()))

    def test_excel_co_du_cot(self):
        self.run_pipeline()
        workbook = load_workbook(self.directory / "danh_sach_thong_bao.xlsx")
        sheet = workbook.active
        headers = [cell.value for cell in sheet[1]]
        self.assertEqual(headers[0], "STT")
        self.assertIn("Số thông báo", headers)
        self.assertIn("File PDF", headers)
        self.assertEqual(sheet.max_row, 4)
        workbook.close()

    def test_chay_lai_khong_tai_lai_pdf(self):
        self.run_pipeline()
        summary, _, state = self.run_pipeline()
        self.assertEqual(summary.downloaded, 3)
        self.assertFalse(state.get("downloads"))

    def test_ma_thong_bao_khong_tao_duong_dan_ngoai_output(self):
        record = parse_tb_records(fixture("tb_results_page1.html"))[0]
        record.so_thong_bao = ""
        for value in ("../../outside", r"..\..\outside", "C:/outside", "nested/name"):
            with self.subTest(value=value):
                record.message_id = value
                name = tb_pdf_filename(record)
                self.assertEqual(Path(name).name, name)
                self.assertNotIn("/", name)
                self.assertNotIn("\\", name)
                self.assertNotIn(":", name)

    def test_tai_lai_thanh_cong_o_doan_sau_giu_ten_file_trong_metadata(self):
        with mock.patch.object(TbPortal, "download_tb", side_effect=[None, TB_PDF, TB_PDF, TB_PDF]):
            summary, _, _ = self.run_pipeline()
        self.assertTrue(summary.complete)
        rows = json.loads((self.directory / "danh_sach_thong_bao.json").read_text("utf-8"))
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["tep_pdf"] and (self.directory / row["tep_pdf"]).is_file() for row in rows))

    def test_dry_run_khong_tai(self):
        summary, _, state = self.run_pipeline(dry_run=True)
        self.assertEqual(summary.discovered, 3)
        self.assertEqual(summary.downloaded, 0)
        self.assertEqual(list(self.directory.glob("*.pdf")), [])
        self.assertFalse(state.get("downloads"))

    def test_trang_lap_lai_thi_bao_loi(self):
        state = {"paged_html": fixture("tb_results_page1.html")}
        with self.assertRaises(SearchError):
            self.run_pipeline(state)


if __name__ == "__main__":
    unittest.main()
