import tempfile
import unittest
from pathlib import Path

import requests

from gdt_tax.errors import NetworkError
from gdt_tax.headers import PROFILE_BROWSER, PROFILE_MINIMAL, build_page_headers
from gdt_tax.http import HttpClient
from gdt_tax.traffic import MASK


class StubResponse:
    def __init__(
        self, status_code: int, headers: dict | None = None, *, text: str = ""
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.content = text.encode("utf-8")
        self.text = text


class FakeSession:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.sent: list[dict] = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        self.sent.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    def close(self):
        self.closed = True


def make_client(responses, **kwargs) -> tuple[HttpClient, FakeSession]:
    session = FakeSession(responses)
    client = HttpClient(
        session=session,
        retries=kwargs.pop("retries", 3),
        min_backoff=0.0,
        default_backoff=0.0,
        **kwargs,
    )
    return client, session


class UrlJoiningTests(unittest.TestCase):
    def test_ghep_duong_dan_tuong_doi(self):
        client, _ = make_client([])
        self.assertEqual(
            client.url("/tchs/thuedientu"), "https://dichvucong.gdt.gov.vn/tthc/tchs/thuedientu"
        )

    def test_giu_nguyen_url_day_du(self):
        client, _ = make_client([])
        self.assertEqual(client.url("https://khac.example/x"), "https://khac.example/x")


class RetryTests(unittest.TestCase):
    def test_thu_lai_khi_bi_gioi_han_tan_suat(self):
        client, session = make_client(
            [
                StubResponse(429, {"Retry-After": "0"}),
                StubResponse(429, {"Retry-After": "0"}),
                StubResponse(200),
            ]
        )
        response = client.get("/tchs")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(session.calls), 3)

    def test_tra_ve_429_o_lan_thu_cuoi(self):
        client, session = make_client(
            [StubResponse(429), StubResponse(429), StubResponse(429)], retries=3
        )
        response = client.get("/tchs")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(session.calls), 3)

    def test_khong_thu_lai_voi_ma_khac(self):
        client, session = make_client([StubResponse(500)])
        self.assertEqual(client.get("/tchs").status_code, 500)
        self.assertEqual(len(session.calls), 1)

    def test_retry_after_sai_dinh_dang_dung_mac_dinh(self):
        client, session = make_client(
            [StubResponse(429, {"Retry-After": "khong-phai-so"}), StubResponse(200)]
        )
        self.assertEqual(client.get("/tchs").status_code, 200)
        self.assertEqual(len(session.calls), 2)

    def test_thu_lai_khi_timeout_tam_thoi(self):
        client, session = make_client(
            [requests.exceptions.ReadTimeout("tam thoi"), StubResponse(200)]
        )
        self.assertEqual(client.get("/tchs").status_code, 200)
        self.assertEqual(len(session.calls), 2)

    def test_bao_loi_mang_sau_khi_dung_het_so_lan_thu(self):
        client, session = make_client(
            [requests.exceptions.ConnectionError("dut ket noi")] * 3
        )
        with self.assertRaisesRegex(NetworkError, "Không gửi được GET"):
            client.get("/tchs")
        self.assertEqual(len(session.calls), 3)

    def test_dong_session(self):
        client, session = make_client([])
        client.close()
        self.assertTrue(session.closed)


class RequestLoggingTests(unittest.TestCase):
    def test_log_info_moi_request(self):
        client, _ = make_client([StubResponse(200, text="halloa")])
        with self.assertLogs("gdt_tax.http", level="INFO") as captured:
            client.get("/tchs/thuedientu", params={"page": 1})
        line = captured.output[0]
        self.assertIn("HTTP GET", line)
        self.assertIn("/tthc/tchs/thuedientu", line)
        self.assertIn("page=1", line)
        self.assertIn("200", line)

    def test_log_debug_co_header_va_body_da_che(self):
        client, _ = make_client([StubResponse(200, text="xin chao")])
        with self.assertLogs("gdt_tax.http", level="DEBUG") as captured:
            client.post(
                "/loginLDAP",
                data={"tenDN": "0101234567-QL", "matKhau": "c2VjcmV0"},
                headers={"Cookie": "JSESSIONID=bi-mat", "User-Agent": "Mozilla/5.0"},
            )
        text = "\n".join(captured.output)
        self.assertIn("GỬI POST", text)
        self.assertIn("Mozilla/5.0", text)
        self.assertIn(MASK, text)
        self.assertNotIn("c2VjcmV0", text)
        self.assertNotIn("bi-mat", text)
        self.assertIn("xin chao", text)

    def test_khong_log_debug_khi_khong_bat(self):
        client, _ = make_client([StubResponse(200)])
        with self.assertLogs("gdt_tax.http", level="INFO") as captured:
            client.get("/tchs")
        self.assertEqual(len(captured.output), 1)


class ExtraHeaderTests(unittest.TestCase):
    def test_header_cau_hinh_ghi_de_header_cua_request(self):
        client, session = make_client(
            [StubResponse(200)],
            extra_headers={"Referer": "https://moi.test/tthc/tchs", "X-Token": "abc"},
        )
        client.get("/tchs", headers={"Referer": "https://cu.test", "Accept": "*/*"})
        sent = session.sent[0]["headers"]
        self.assertEqual(sent["Referer"], "https://moi.test/tthc/tchs")
        self.assertEqual(sent["X-Token"], "abc")
        self.assertEqual(sent["Accept"], "*/*")

    def test_khong_co_header_cau_hinh_thi_giu_nguyen(self):
        client, session = make_client([StubResponse(200)], header_profile=PROFILE_MINIMAL)
        client.get("/tchs", headers={"Referer": "https://cu.test"})
        self.assertEqual(session.sent[0]["headers"], {"Referer": "https://cu.test"})

    def test_header_cau_hinh_van_thang_header_mac_dinh_cua_browser(self):
        client, session = make_client(
            [StubResponse(200)],
            header_profile=PROFILE_BROWSER,
            extra_headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/153"},
        )
        client.get("/tchs")
        self.assertIn("X11; Linux", session.sent[0]["headers"]["User-Agent"])

    def test_client_hint_duoc_dat_lai_theo_user_agent_ghi_de(self):
        client, session = make_client(
            [StubResponse(200)],
            extra_headers={"User-Agent": "Mozilla/5.0 Firefox/140.0"},
        )
        client.get("/tchs", headers=build_page_headers(profile=PROFILE_BROWSER))
        sent = session.sent[0]["headers"]
        self.assertEqual(sent["User-Agent"], "Mozilla/5.0 Firefox/140.0")
        self.assertNotIn("sec-ch-ua", sent)
        self.assertEqual(sent["Sec-Fetch-Dest"], "document")

    def test_file_dump_ghi_ca_header_mac_dinh_cua_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = FakeSession([StubResponse(200)])
            session.headers = {"User-Agent": "python-requests/2.32"}
            client = HttpClient(
                session=session,
                retries=1,
                min_backoff=0.0,
                default_backoff=0.0,
                dump_dir=tmp,
                header_profile=PROFILE_MINIMAL,
            )
            client.get("/tchs", headers={"Accept": "text/html-partial"})
            request_text = next(Path(tmp).rglob("*.request.txt")).read_text(encoding="utf-8")

        self.assertIn("User-Agent: python-requests/2.32", request_text)
        self.assertIn("Accept: text/html-partial", request_text)


class HeaderProfileAtClientTests(unittest.TestCase):
    def test_browser_xoa_header_mac_dinh_cua_requests(self):
        session = FakeSession([StubResponse(200)])
        session.headers = {
            "User-Agent": "python-requests/2.32",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        HttpClient(session=session, retries=1)
        self.assertEqual(dict(session.headers), {})

    def test_browser_giu_header_tuy_bien_cua_session(self):
        session = FakeSession([StubResponse(200)])
        session.headers = {"User-Agent": "python-requests/2.32", "X-Noi-Bo": "1"}
        HttpClient(session=session, retries=1)
        self.assertEqual(dict(session.headers), {"X-Noi-Bo": "1"})

    def test_browser_bu_bo_header_toi_thieu_khi_goi_tran(self):
        client, session = make_client([StubResponse(200)], header_profile=PROFILE_BROWSER)
        client.get("/tchs")
        sent = session.sent[0]["headers"]
        self.assertIn("Chrome/153", sent["User-Agent"])
        self.assertNotIn("python-requests", str(sent))
        self.assertEqual(sent["Accept-Language"], "vi,en-US;q=0.9,en;q=0.8")
        self.assertTrue(sent["Accept-Encoding"].startswith("gzip, deflate"))

    def test_browser_sap_xep_lai_header_theo_thu_tu_chrome(self):
        client, session = make_client(
            [StubResponse(200)],
            header_profile=PROFILE_BROWSER,
            extra_headers={"Referer": "https://x.test/tthc/tchs"},
        )
        client.get("/tchs", headers={"HX-Request": "true"})
        sent = session.sent[0]["headers"]
        names = list(sent)
        self.assertLess(names.index("User-Agent"), names.index("Accept"))
        self.assertLess(names.index("Accept"), names.index("Referer"))
        self.assertLess(names.index("Referer"), names.index("Accept-Encoding"))

    def test_minimal_khong_dung_toi_session(self):
        session = FakeSession([StubResponse(200)])
        session.headers = {"User-Agent": "python-requests/2.32"}
        HttpClient(session=session, retries=1, header_profile=PROFILE_MINIMAL)
        self.assertEqual(dict(session.headers), {"User-Agent": "python-requests/2.32"})


class DumpTests(unittest.TestCase):
    def test_dump_http_ghi_file_theo_tung_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = make_client([StubResponse(200, text="<html>ket qua</html>")], dump_dir=tmp)
            client.get("/tchs")
            written = sorted(Path(tmp).rglob("*.txt"))
            self.assertEqual(len(written), 2)
            self.assertTrue(written[0].name.endswith(".request.txt"))
            self.assertTrue(written[1].name.endswith(".response.txt"))
            self.assertIn("<html>ket qua</html>", written[1].read_text(encoding="utf-8"))

    def test_khong_dump_thi_khong_tao_thu_muc(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = make_client([StubResponse(200)])
            client.get("/tchs")
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
