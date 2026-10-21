import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from gdt_tax.traffic import (
    MASK,
    TrafficDumper,
    describe_body,
    describe_params,
    format_size,
    mask_data,
    mask_headers,
    slug,
)


class StubResponse:
    def __init__(self, text="", *, status_code=200, content=None, headers=None) -> None:
        self.status_code = status_code
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.headers = headers or {}


class MaskHeadersTests(unittest.TestCase):
    def test_che_header_phien_dang_nhap(self):
        masked = mask_headers(
            {
                "User-Agent": "Mozilla/5.0",
                "Cookie": "JSESSIONID=bi-mat",
                "Set-Cookie": "XSRF=x",
                "Authorization": "Bearer bi-mat",
                "X-XSRF-TOKEN": "token-that",
            }
        )
        self.assertEqual(masked["User-Agent"], "Mozilla/5.0")
        self.assertEqual(masked["Cookie"], MASK)
        self.assertEqual(masked["Set-Cookie"], MASK)
        self.assertEqual(masked["Authorization"], MASK)
        self.assertEqual(masked["X-XSRF-TOKEN"], MASK)

    def test_chap_nhan_header_rong(self):
        self.assertEqual(mask_headers(None), {})
        self.assertEqual(mask_headers({}), {})


class MaskDataTests(unittest.TestCase):
    def test_che_mat_khau_va_csrf_trong_form(self):
        masked = mask_data({"tenDN": "0101234567-QL", "matKhau": "c2VjcmV0", "_csrf": "token"})
        self.assertEqual(masked["tenDN"], MASK)
        self.assertEqual(masked["matKhau"], MASK)
        self.assertEqual(masked["_csrf"], MASK)

    def test_che_form_dang_danh_sach(self):
        masked = mask_data([("tenDN", "abc"), ("matKhau", "c2VjcmV0")])
        self.assertEqual(masked, [("tenDN", MASK), ("matKhau", MASK)])

    def test_che_long_trong_dict_con(self):
        masked = mask_data({"auth": {"password": "bi-mat", "user": "abc"}})
        self.assertEqual(masked["auth"], {"password": MASK, "user": "abc"})


class DescribeBodyTests(unittest.TestCase):
    def test_bytes_khong_giai_ma_duoc_khong_lam_vo(self):
        self.assertIn("\ufffd", describe_body(b"\xff\xfe khong-phai-utf8"))

    def test_cat_bot_body_dai(self):
        text = describe_body({"a": "x" * 50}, limit=20)
        self.assertTrue(text.startswith("{"))
        self.assertIn("ký tự)", text)

    def test_body_rong(self):
        self.assertEqual(describe_body(None), "")
        self.assertEqual(describe_body(""), "")


class DescribeParamsTests(unittest.TestCase):
    def test_ghi_giong_query_string(self):
        self.assertEqual(describe_params({"page": 1, "size": 10}), "page=1&size=10")

    def test_che_tham_so_nhay_cam(self):
        self.assertEqual(describe_params({"captcha": "abcde", "_csrf": "token"}), "captcha=***&_csrf=***")

    def test_cat_bot_khi_qua_dai(self):
        text = describe_params({"tuNgay": "0" * 50}, limit=10)
        self.assertEqual(text, "tuNgay=***")


class FormatSizeTests(unittest.TestCase):
    def test_cac_moc_dung_luong(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(812), "812 B")
        self.assertEqual(format_size(2048), "2.0 kB")
        self.assertEqual(format_size(3 * 1024 * 1024), "3.0 MB")


class SlugTests(unittest.TestCase):
    def test_bo_scheme_va_host(self):
        self.assertEqual(
            slug("https://dichvucong.gdt.gov.vn/tthc/ho-so/search"), "tthc-ho-so-search"
        )

    def test_bo_query_string(self):
        self.assertEqual(slug("https://x.test/tthc/tchs?page=1"), "tthc-tchs")

    def test_goc_tra_ve_root(self):
        self.assertEqual(slug("https://x.test/"), "root")


class TrafficDumperTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def make_dumper(self, **kwargs) -> TrafficDumper:
        kwargs.setdefault("clock", lambda: datetime(2026, 9, 25, 10, 30, 0))
        return TrafficDumper(self.directory, **kwargs)

    def test_tao_thu_muc_con_theo_thoi_diem(self):
        dumper = self.make_dumper()
        dumper.record(method="GET", url="https://x.test/tthc/tchs", response=StubResponse("ok"))
        self.assertEqual(dumper.root, self.directory / "20260925-103000")
        self.assertTrue(dumper.root.is_dir())

    def test_ghi_request_va_response_da_che(self):
        dumper = self.make_dumper()
        paths = dumper.record(
            method="post",
            url="https://x.test/tthc/loginLDAP",
            params={"page": 1},
            headers={"Cookie": "JSESSIONID=bi-mat", "User-Agent": "Mozilla/5.0"},
            body={"tenDN": "abc", "matKhau": "c2VjcmV0"},
            response=StubResponse('{"status": "200"}', headers={"Set-Cookie": "XSRF=x"}),
            elapsed=0.5,
        )
        self.assertEqual([path.suffix for path in paths], [".txt", ".txt"])

        request_text = paths[0].read_text(encoding="utf-8")
        response_text = paths[1].read_text(encoding="utf-8")

        self.assertIn("POST https://x.test/tthc/loginLDAP", request_text)
        self.assertIn("Cookie: ***", request_text)
        self.assertIn("User-Agent: Mozilla/5.0", request_text)
        self.assertIn("payload omitted", request_text)
        self.assertNotIn('"tenDN"', request_text)
        self.assertNotIn("c2VjcmV0", request_text)
        self.assertIn("tham số: page=1", request_text)

        self.assertIn("HTTP 200 (0.50s", response_text)
        self.assertIn("Set-Cookie: ***", response_text)
        self.assertIn("payload omitted", response_text)
        self.assertNotIn('"status": "200"', response_text)

    def test_danh_so_file_tang_dan_theo_thu_tu_goi(self):
        dumper = self.make_dumper()
        first = dumper.record(method="GET", url="https://x.test/tthc/tchs", response=StubResponse())
        second = dumper.record(method="GET", url="https://x.test/tthc/tchs", response=StubResponse())
        self.assertTrue(first[0].name.startswith("0001-"))
        self.assertTrue(second[0].name.startswith("0002-"))

    def test_khong_ghi_file_body_khi_rong(self):
        dumper = self.make_dumper()
        paths = dumper.record(
            method="GET",
            url="https://x.test/tthc/tchs",
            response=StubResponse(content=b""),
        )
        self.assertEqual([path.suffix for path in paths], [".txt", ".txt"])

    def test_body_qua_lon_thi_chi_giu_phan_dau(self):
        dumper = self.make_dumper(max_body_bytes=16, private=True)
        paths = dumper.record(
            method="GET",
            url="https://x.test/tthc/tchs",
            response=StubResponse(content=b"x" * 100),
        )
        self.assertEqual(paths[2].read_bytes(), b"x" * 16)
        self.assertTrue((dumper.root / "PRIVATE.txt").exists())

    def test_ghi_them_nhieu_lan_chay_khong_ghi_de(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = TrafficDumper(tmp, clock=lambda: datetime(2026, 9, 25, 10, 0, 0))
            second = TrafficDumper(tmp, clock=lambda: datetime(2026, 9, 25, 11, 0, 0))
            first.record(method="GET", url="https://x.test/tthc/tchs", response=StubResponse("a"))
            second.record(method="GET", url="https://x.test/tthc/tchs", response=StubResponse("b"))
            self.assertTrue((Path(tmp) / "20260925-100000").is_dir())
            self.assertTrue((Path(tmp) / "20260925-110000").is_dir())


if __name__ == "__main__":
    unittest.main()
