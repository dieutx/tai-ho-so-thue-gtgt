"""Test luồng chạy đầy đủ, hoàn toàn offline.

:class:`tests.support.FakeHttp` thay cho lớp HTTP thật, nên các test này chạy
được cả trên CI mà không cần tài khoản hay kết nối Internet, đồng thời vẫn đi
qua đúng code của portal, storage và pipeline.
"""

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from gdt_tax.config import Settings
from gdt_tax.constants import (
    DVC_DOWNLOAD,
    DVC_SEARCH,
    DVC_VALIDATE,
    ETAX_DOWNLOAD,
    ETAX_SEARCH,
    LANDING,
    LOGIN_CAPTCHA,
    LOGIN_ENDPOINT,
    LOGIN_PAGE,
    SEARCH_CAPTCHA,
)
from gdt_tax.errors import LoginError, SearchError
from gdt_tax.naming import zip_filename
from gdt_tax.parsing import parse_records
from gdt_tax.pipeline import Pipeline
from gdt_tax.storage import ZipStore
from tests.support import (
    DETAIL_HTML,
    FAKE_CAPTCHA_BYTES,
    LANDING_HTML,
    LOGIN_HTML,
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    fixture,
    route_of,
    sample_zip,
    zip_payload,
)

IMAGE_HEADERS = {"content-type": "image/png"}


def make_handler(*, search, download_ok: bool = True):
    """Dựng handler giả cho toàn bộ endpoint mà pipeline dùng."""

    def handler(method, path, kwargs):
        route = route_of(path)
        if route == LOGIN_PAGE and method == "GET":
            return FakeResponse(LOGIN_HTML)
        if route == LOGIN_CAPTCHA:
            return FakeResponse(content=FAKE_CAPTCHA_BYTES, headers=IMAGE_HEADERS)
        if route == LOGIN_ENDPOINT:
            return FakeResponse(json_payload={"status": "200"})
        if route == LANDING:
            return FakeResponse(LANDING_HTML)
        if route == SEARCH_CAPTCHA:
            return FakeResponse(content=FAKE_CAPTCHA_BYTES, headers=IMAGE_HEADERS)
        if route in (ETAX_SEARCH, DVC_SEARCH):
            return FakeResponse(search(kwargs))
        if route.startswith("/tchs/files/detail/"):
            return FakeResponse(DETAIL_HTML)
        if route == ETAX_DOWNLOAD:
            if not download_ok:
                return FakeResponse("loi may chu", status_code=500)
            return FakeResponse(
                json_payload={"content": zip_payload(), "fileName": "to-khai.zip"}
            )
        if route == DVC_VALIDATE:
            return FakeResponse("200")
        if route == DVC_DOWNLOAD:
            if not download_ok:
                return FakeResponse("loi may chu", status_code=500)
            return FakeResponse(json_payload={"content": zip_payload()})
        return None

    return handler


def etax_search(_kwargs) -> str:
    return fixture("etax_results.html")


class PipelineTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def settings_for(self, **overrides) -> Settings:
        values = dict(
            username="0101234567-QL",
            password="mat-khau",
            from_date=date(2025, 1, 1),
            to_date=date(2025, 1, 31),
            download_dir=self.directory,
            login_attempts=1,
            search_attempts=1,
            pause_between_records=0.0,
            pause_between_pages=0.0,
        )
        values.update(overrides)
        return Settings(**values)

    def run_pipeline(self, handler, settings=None):
        settings = settings or self.settings_for()
        http = FakeHttp(handler)
        pipeline = Pipeline(
            settings,
            http,
            StubCaptcha(),
            store=ZipStore(settings.download_dir),
            sleep=lambda _seconds: None,
        )
        return pipeline.run(), http


class EtaxFlowTests(PipelineTestCase):
    def test_tai_du_hai_ho_so(self):
        summary, _ = self.run_pipeline(make_handler(search=etax_search))
        self.assertEqual(summary.periods, 1)
        self.assertEqual(summary.expected, 2)
        self.assertEqual(summary.downloaded, 2)
        self.assertTrue(summary.complete)

        names = sorted(path.name for path in self.directory.glob("*.zip"))
        self.assertEqual(len(names), 2)
        self.assertTrue(all("Chinh-thuc" in name for name in names))
        self.assertTrue(any("Hoat-dong" in name for name in names))

    def test_goi_dung_tham_so_tra_cuu_etax(self):
        _, http = self.run_pipeline(make_handler(search=etax_search))
        calls = [call for call in http.calls if route_of(call.path) == ETAX_SEARCH]
        self.assertEqual(len(calls), 1)

        data = calls[0].kwargs["data"]
        self.assertEqual(data["tuNgay_tdt"], "01/01/2025")
        self.assertEqual(data["denNgay_tdt"], "31/01/2025")
        self.assertEqual(data["_csrf"], "csrf-landing")
        self.assertEqual(data["captcha"], "abcde")
        self.assertEqual(data["size"], 10)

        headers = calls[0].kwargs["headers"]
        self.assertEqual(headers["HX-Target"], "bangKetQuaTraCuu_tdt")
        self.assertEqual(headers["X-XSRF-TOKEN"], "csrf-landing")

    def test_goi_dung_endpoint_tai_etax(self):
        _, http = self.run_pipeline(make_handler(search=etax_search))
        downloads = [call for call in http.calls if route_of(call.path) == ETAX_DOWNLOAD]
        self.assertEqual(len(downloads), 2)
        self.assertEqual(downloads[0].kwargs["params"], {"loaiTraCuu": "ETAX"})
        self.assertEqual(downloads[0].kwargs["json"], {"maHoSo": "11320250292469209"})
        self.assertEqual(downloads[0].kwargs["headers"]["X-XSRF-TOKEN"], "csrf-detail")

        details = [
            call for call in http.calls if route_of(call.path).startswith("/tchs/files/detail/")
        ]
        self.assertEqual(len(details), 2)
        self.assertTrue(all(call.path.endswith("?loai=ETAX") for call in details))

    def test_ghi_metadata_sau_khi_tai(self):
        self.run_pipeline(make_handler(search=etax_search))
        csv_path = self.directory / "danh_sach_ho_so.csv"
        json_path = self.directory / "danh_sach_ho_so.json"
        self.assertTrue(csv_path.is_file())
        self.assertTrue(json_path.is_file())

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["loai_to_khai"], "Chính thức")
        self.assertEqual(payload[0]["nguon"], "ETAX")
        self.assertTrue(payload[0]["tep_zip"].endswith(".zip"))

    def test_bo_qua_zip_da_tai(self):
        for record in parse_records(fixture("etax_results.html"), "ETAX"):
            (self.directory / zip_filename(record)).write_bytes(sample_zip())

        summary, http = self.run_pipeline(make_handler(search=etax_search))
        self.assertEqual(summary.downloaded, 2)
        downloads = [call for call in http.calls if route_of(call.path) == ETAX_DOWNLOAD]
        self.assertEqual(downloads, [])

    def test_dry_run_chi_tra_cuu(self):
        settings = self.settings_for(dry_run=True)
        summary, http = self.run_pipeline(make_handler(search=etax_search), settings)
        self.assertEqual(summary.expected, 2)
        self.assertEqual(summary.downloaded, 0)
        self.assertFalse(summary.complete)
        self.assertEqual(list(self.directory.glob("*.zip")), [])
        self.assertTrue((self.directory / "danh_sach_ho_so.json").is_file())

    def test_case_id_chi_tai_mot_ho_so(self):
        settings = self.settings_for(case_id="11320250292528963")
        summary, http = self.run_pipeline(make_handler(search=etax_search), settings)
        self.assertEqual(summary.expected, 1)
        self.assertEqual(summary.downloaded, 1)

        downloads = [call for call in http.calls if route_of(call.path) == ETAX_DOWNLOAD]
        self.assertEqual(len(downloads), 1)
        self.assertEqual(downloads[0].kwargs["json"]["maHoSo"], "11320250292528963")

    def test_loi_tai_khong_lam_dung_chuong_trinh(self):
        summary, _ = self.run_pipeline(make_handler(search=etax_search, download_ok=False))
        self.assertEqual(summary.expected, 2)
        self.assertEqual(summary.downloaded, 0)
        self.assertFalse(summary.complete)


class DvcFlowTests(PipelineTestCase):
    def dvc_settings(self) -> Settings:
        return self.settings_for(from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))

    def test_phan_trang_va_tai_du_ho_so(self):
        def search(kwargs) -> str:
            page = kwargs.get("params", {}).get("page")
            return fixture("dvc_results_page1.html" if page == 1 else "dvc_results_page2.html")

        summary, http = self.run_pipeline(make_handler(search=search), self.dvc_settings())
        self.assertEqual(summary.expected, 2)
        self.assertEqual(summary.downloaded, 2)

        pages = [call.kwargs["params"]["page"] for call in http.calls if route_of(call.path) == DVC_SEARCH]
        self.assertEqual(pages, [1, 2])

        dates = [call.kwargs["params"] for call in http.calls if route_of(call.path) == DVC_SEARCH][0]
        self.assertEqual(dates["tuNgay"], "01/01/2026")
        self.assertEqual(dates["denNgay"], "31/01/2026")

    def test_di_qua_buoc_kiem_tra_truoc_khi_tai(self):
        def search(_kwargs) -> str:
            return fixture("dvc_results_page1.html")

        _, http = self.run_pipeline(make_handler(search=search), self.dvc_settings())
        validates = [call for call in http.calls if route_of(call.path) == DVC_VALIDATE]
        downloads = [call for call in http.calls if route_of(call.path) == DVC_DOWNLOAD]
        self.assertEqual(len(validates), 2)
        self.assertEqual(len(downloads), 2)
        self.assertEqual(downloads[0].kwargs["json"], {"maHoSo": "G12.18-260120-21010800254723"})

        details = [
            call for call in http.calls if route_of(call.path).startswith("/tchs/files/detail/")
        ]
        self.assertTrue(all(call.path.endswith("?loai=") for call in details))


class FailureTests(PipelineTestCase):
    def test_dang_nhap_that_bai_thi_bao_loi(self):
        def handler(method, path, kwargs):
            route = route_of(path)
            if route == LOGIN_PAGE:
                return FakeResponse(LOGIN_HTML)
            if route == LOGIN_CAPTCHA:
                return FakeResponse(content=FAKE_CAPTCHA_BYTES, headers=IMAGE_HEADERS)
            if route == LOGIN_ENDPOINT:
                return FakeResponse(json_payload={"status": "500"})
            return None

        with mock.patch("gdt_tax.auth.time.sleep"):
            with self.assertRaises(LoginError):
                self.run_pipeline(handler)

    def test_khong_tim_duoc_trang_thi_bao_loi(self):
        handler = make_handler(search=lambda _kwargs: "<div></div>")
        with self.assertRaises(SearchError):
            self.run_pipeline(handler)


if __name__ == "__main__":
    unittest.main()
