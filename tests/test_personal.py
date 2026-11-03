"""Test luồng tài khoản cá nhân, hoàn toàn offline.

``FakeHttp`` thay cho ``HttpClient`` nên test đi qua đúng code portal, parsing,
pipeline và lưu metadata mà không cần tài khoản hay Internet.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from gdt_tax.auth import login
from gdt_tax.config import Settings
from gdt_tax.constants import (
    ACCOUNT_PERSONAL,
    CANHAN_REQUEST,
    DVC_DOWNLOAD,
    DVC_SEARCH,
    DVC_SSO_REDIRECT,
    DVC_VALIDATE,
    LANDING,
    LOGIN_CAPTCHA,
    LOGIN_ENDPOINT,
    LOGIN_PAGE,
    SEARCH_CAPTCHA,
    SOURCE_CANHAN,
    SOURCE_DVC_PERSONAL,
)
from gdt_tax.errors import ConfigError, StorageError
from gdt_tax.models import SearchPeriod
from gdt_tax.parsing import page_count, parse_records
from gdt_tax.pipeline import Pipeline
from gdt_tax.portals import build_portals
from gdt_tax.portals.personal import CanhanNoticePortal, DvcPersonalPortal
from gdt_tax.storage import decode_zip_bytes
from gdt_tax.taxpayer import Taxpayer, parse_taxpayer, save_taxpayer
from tests.support import (
    DETAIL_HTML,
    FAKE_CAPTCHA_BYTES,
    LOGIN_HTML,
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    cleanup_temporary_directory,
    fixture,
    route_of,
    zip_payload,
)

IMAGE_HEADERS = {"content-type": "image/png"}
PDF_BYTES = b"%PDF-1.4\n% thong bao test\n"
CANHAN_URL = "https://canhan.gdt.gov.vn/ICanhan/"


def make_handler(state: dict):
    """Handler giả cho đăng nhập CN, tờ khai DVC và thông báo cổng cá nhân."""

    def handler(method, path, kwargs):
        route = route_of(path)
        if route == LOGIN_PAGE and method == "GET":
            return FakeResponse(LOGIN_HTML)
        if route == LOGIN_CAPTCHA:
            return FakeResponse(content=FAKE_CAPTCHA_BYTES, headers=IMAGE_HEADERS)
        if route == LOGIN_ENDPOINT:
            state["login"] = dict(kwargs.get("data") or {})
            return FakeResponse(json_payload={"status": "200"})
        if route == LANDING:
            return FakeResponse(fixture("personal_landing.html"))
        if route == SEARCH_CAPTCHA:
            return FakeResponse(content=FAKE_CAPTCHA_BYTES, headers=IMAGE_HEADERS)
        if route == DVC_SEARCH:
            state.setdefault("searches", []).append(dict(kwargs.get("params") or {}))
            return FakeResponse(fixture("personal_dvc_results.html"))
        if route.startswith("/tchs/files/detail/"):
            return FakeResponse(DETAIL_HTML)
        if route == DVC_VALIDATE:
            return FakeResponse("200")
        if route == DVC_DOWNLOAD:
            return FakeResponse(json_payload={"content": zip_payload()})
        if route == DVC_SSO_REDIRECT:
            state["sso"] = dict(kwargs.get("params") or {})
            return FakeResponse(
                "https://canhan.gdt.gov.vn/ICanhan/?vnconnect=SSOTHUE&code=TEST&module=10607"
            )
        if route.startswith("/ICanhan/"):
            if route.endswith("/EstablishSession"):
                return FakeResponse(fixture("canhan_index.html"), url=CANHAN_URL + "EstablishSession")
            if method == "GET":
                if route == "/ICanhan/":
                    return FakeResponse(fixture("canhan_index.html"), url=CANHAN_URL)
                return FakeResponse(fixture("canhan_handoff.html"), url=CANHAN_REQUEST)
            data = kwargs.get("data") or {}
            event = str(data.get("dse_nextEventName", ""))
            operation = str(data.get("dse_operationName", ""))
            if event == "startSSOTTHC":
                return FakeResponse(fixture("canhan_handoff.html"), url=CANHAN_REQUEST)
            if operation == "retailSearchTaxNoticesProc" and event == "start":
                return FakeResponse(fixture("canhan_search.html"), url=CANHAN_REQUEST)
            if event == "ok":
                state["notice_search"] = dict(data)
                return FakeResponse(fixture("canhan_notices.html"), url=CANHAN_REQUEST)
            if event == "download":
                state["notice_download"] = dict(data)
                return FakeResponse(
                    content=PDF_BYTES,
                    headers={
                        "content-type": "application/octet-stream",
                        "content-disposition": "attachment;filename=thongbao.pdf",
                    },
                )
            return FakeResponse(fixture("canhan_handoff.html"), url=CANHAN_REQUEST)
        return None

    return handler


def personal_settings(directory: Path, **overrides) -> Settings:
    values = dict(
        username="0123456789",
        password="mat-khau",
        from_date=date(2025, 10, 1),
        to_date=date(2025, 10, 31),
        download_dir=directory,
        account_type=ACCOUNT_PERSONAL,
        login_attempts=1,
        search_attempts=1,
        pause_between_records=0.0,
        pause_between_pages=0.0,
    )
    values.update(overrides)
    return Settings(**values)


def period() -> SearchPeriod:
    return SearchPeriod(start=date(2025, 10, 1), end=date(2025, 10, 31), source=SOURCE_CANHAN)


class TaxpayerTests(unittest.TestCase):
    def test_doc_ten_va_so_dinh_danh(self):
        taxpayer = parse_taxpayer(fixture("personal_landing.html"), "0123456789")
        self.assertIsNotNone(taxpayer)
        self.assertEqual(taxpayer.mst, "0123456789")
        self.assertEqual(taxpayer.ten_nguoi_nop_thue, "NGUYEN VAN A")

    def test_doanh_nghiep_dung_ma_so_thue_va_bo_qua_script(self):
        html = (
            '<span class="ten_dn">CONG TY MAU</span>'
            "<span>Mã số thuế: 0101350748</span>"
            '<script>taikhoan khac: "9999999999"</script>'
        )
        taxpayer = parse_taxpayer(html)
        self.assertEqual(taxpayer.mst, "0101350748")
        self.assertEqual(taxpayer.ten_nguoi_nop_thue, "CONG TY MAU")

    def test_dung_username_khi_trang_khong_in_nhan(self):
        taxpayer = parse_taxpayer('<span class="ten_dn">CONG TY MAU</span>', "0101350748-QL")
        self.assertEqual(taxpayer.mst, "0101350748")

    def test_trang_khong_co_ten_thi_bo_qua(self):
        self.assertIsNone(parse_taxpayer("<html></html>", "0123456789"))

    def test_luu_va_gop_theo_mst(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_taxpayer(tmp, Taxpayer("0123456789", "NGUYEN VAN A"))
            save_taxpayer(tmp, Taxpayer("0101350748", "CONG TY MAU"))
            save_taxpayer(
                tmp,
                Taxpayer("0123456789", "NGUYEN VAN B"),
                now=datetime(2026, 11, 3, 9, 30, 0),
            )
            payload = json.loads(
                (Path(tmp) / "nguoi_nop_thue.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["schema_version"], 1)
            entries = payload["nguoi_nop_thue"]
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries["0123456789"]["ten_nguoi_nop_thue"], "NGUYEN VAN B")
            self.assertEqual(entries["0101350748"]["ten_nguoi_nop_thue"], "CONG TY MAU")
            self.assertEqual(entries["0123456789"]["cap_nhat"], "2026-11-03T09:30:00")

    def test_file_hong_khong_bi_ghi_de(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nguoi_nop_thue.json"
            path.write_text("{khong-phai-json", encoding="utf-8")
            with self.assertRaises(StorageError):
                save_taxpayer(tmp, Taxpayer("0123456789", "NGUYEN VAN A"))
            self.assertEqual(path.read_text(encoding="utf-8"), "{khong-phai-json")


class PersonalConfigTests(unittest.TestCase):
    def test_moi_doan_ngay_chay_ca_hai_nguon_ca_nhan(self):
        settings = personal_settings(Path("download"))
        periods = settings.periods()
        self.assertEqual([item.source for item in periods], [SOURCE_DVC_PERSONAL, SOURCE_CANHAN])
        self.assertTrue(all(item.start == date(2025, 10, 1) for item in periods))

    def test_chi_bat_hai_nguon_ca_nhan(self):
        settings = personal_settings(Path("download"))
        self.assertTrue(settings.source_enabled(SOURCE_DVC_PERSONAL))
        self.assertTrue(settings.source_enabled(SOURCE_CANHAN))
        self.assertFalse(settings.source_enabled("DVC"))
        self.assertFalse(settings.source_enabled("ETAX_LEGACY"))

    def test_loai_tai_khoan_sai_bi_tu_choi(self):
        with self.assertRaises(ConfigError):
            personal_settings(Path("download"), account_type="ca-nhan").validate()

    def test_build_portals_chi_tra_ve_nguon_ca_nhan(self):
        settings = personal_settings(Path("download"))
        portals = build_portals(FakeHttp(lambda *args: None), StubCaptcha(), settings, "csrf")
        self.assertEqual(set(portals), {SOURCE_DVC_PERSONAL, SOURCE_CANHAN})
        self.assertIsInstance(portals[SOURCE_DVC_PERSONAL], DvcPersonalPortal)
        self.assertIsInstance(portals[SOURCE_CANHAN], CanhanNoticePortal)


class NoticeParsingTests(unittest.TestCase):
    def test_doc_thong_bao_va_id_tai(self):
        records = parse_records(fixture("canhan_notices.html"), SOURCE_CANHAN)
        self.assertEqual(len(records), 2)
        first = records[0]
        self.assertEqual(first.ma_ho_so, "81214446")
        self.assertEqual(first.so_thong_bao, "96356/TB-TCS4-KDT")
        self.assertEqual(first.ma_loai_thong_bao, "KDT")
        self.assertEqual(first.ngay_nop, "15/10/2025")
        self.assertEqual(first.nguon, SOURCE_CANHAN)
        self.assertEqual(first.loai_tai_lieu, "NOTICE")

    def test_tong_so_trang(self):
        self.assertEqual(page_count(fixture("canhan_notices.html"), SOURCE_CANHAN), 1)
        self.assertEqual(page_count(fixture("canhan_search.html"), SOURCE_CANHAN), 1)


class LoginDoiTuongTests(unittest.TestCase):
    def run_login(self, **overrides) -> dict:
        state: dict = {}
        http = FakeHttp(make_handler(state))
        self.assertTrue(login(http, StubCaptcha(), personal_settings(Path("download"), **overrides)))
        return state["login"]

    def test_tai_khoan_ca_nhan_gui_doi_tuong_cn(self):
        self.assertEqual(self.run_login()["doiTuong"], "CN")

    def test_tai_khoan_doanh_nghiep_mac_dinh_dn(self):
        self.assertEqual(self.run_login(account_type="business")["doiTuong"], "DN")


class DvcPersonalPortalTests(unittest.TestCase):
    def test_tra_cuu_scope_self_va_ghi_nguon_ca_nhan(self):
        state: dict = {}
        portal = DvcPersonalPortal(
            FakeHttp(make_handler(state)),
            StubCaptcha(),
            personal_settings(Path("download")),
        )
        result = portal.search(
            SearchPeriod(date(2025, 10, 1), date(2025, 10, 31), SOURCE_DVC_PERSONAL), 1
        )
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].nguon, SOURCE_DVC_PERSONAL)
        self.assertEqual(result.total_pages, 1)
        self.assertEqual(state["searches"][0]["scope_tdt1"], "SELF")
        self.assertEqual(state["searches"][0]["tuNgay"], "01/10/2025")


class CanhanPortalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.state: dict = {}
        self.portal = CanhanNoticePortal(
            FakeHttp(make_handler(self.state)),
            StubCaptcha(),
            personal_settings(self.directory),
            csrf="csrf-token",
        )

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def test_mo_phien_bang_sso_module_10607(self):
        self.portal.login()
        self.assertTrue(self.portal._logged_in)
        self.assertEqual(self.state["sso"], {"module": "10607"})

    def test_tim_thong_bao_va_tai_pdf_trong_zip(self):
        result = self.portal.search(period(), 1)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.total_pages, 1)
        self.assertEqual(self.state["notice_search"]["_ngaygui"], "01/10/2025")
        self.assertEqual(self.state["notice_search"]["_denngay"], "31/10/2025")
        self.assertEqual(self.state["notice_search"]["maGDichArr"], ";;;;;;;;;")

        record = result.records[0]
        detail_url, csrf = self.portal.fetch_detail_csrf(record)
        self.assertEqual(csrf, "")
        response = self.portal.download(record, detail_url, csrf)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.state["notice_download"]["idTBao"], "81214446")
        self.assertEqual(self.state["notice_download"]["loaitbao"], "KDT")

        data = decode_zip_bytes(response)
        self.assertIsNotNone(data)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            self.assertEqual(archive.namelist(), ["thongbao.pdf"])
            self.assertEqual(archive.read("thongbao.pdf"), PDF_BYTES)


class PersonalPipelineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def test_chay_du_hai_nguon_va_luu_ten_theo_mst(self):
        state: dict = {}
        http = FakeHttp(make_handler(state))
        summary = Pipeline(
            personal_settings(self.directory),
            http,
            StubCaptcha(),
            sleep=lambda _seconds: None,
        ).run()

        self.assertEqual(summary.expected, 3)
        self.assertEqual(summary.downloaded, 3)
        self.assertTrue(summary.complete)
        self.assertEqual(state["login"]["doiTuong"], "CN")
        self.assertEqual(state["sso"]["module"], "10607")

        registry = json.loads(
            (self.directory / "nguoi_nop_thue.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            registry["nguoi_nop_thue"]["0123456789"]["ten_nguoi_nop_thue"], "NGUYEN VAN A"
        )

        rows = json.loads(
            (self.directory / "danh_sach_ho_so.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {row["nguon"] for row in rows}, {SOURCE_DVC_PERSONAL, SOURCE_CANHAN}
        )
        self.assertTrue(all(row["mst"] == "0123456789" for row in rows))
        self.assertTrue(all(row["ten_nguoi_nop_thue"] == "NGUYEN VAN A" for row in rows))
        self.assertEqual(len(list(self.directory.glob("*.zip"))), 3)


if __name__ == "__main__":
    unittest.main()
