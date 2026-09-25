import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from gdt_tax.errors import ConfigError, NetworkError
from gdt_tax.http import HttpClient
from gdt_tax.proxy import SOCKS_HINT, Proxy, _has_pysocks, parse_proxy
from gdt_tax.traffic import mask_secrets

#: Dạng "host:port:tài-khoản:mật-khẩu" mà nhiều nhà cung cấp proxy Việt Nam đưa.
#: Dùng địa chỉ giả — không bao giờ dán proxy thật của bạn vào test hay tài liệu.
VN_PROXY = "1.2.3.4:8080:nha-cung-cap:bi-mat-proxy"


class ParseProxyTests(unittest.TestCase):
    def test_dang_bon_truong_cua_nha_cung_cap(self):
        proxy = parse_proxy(VN_PROXY)
        self.assertEqual(proxy.host, "1.2.3.4")
        self.assertEqual(proxy.port, 8080)
        self.assertEqual(proxy.username, "nha-cung-cap")
        self.assertEqual(proxy.password, "bi-mat-proxy")
        self.assertEqual(proxy.scheme, "http")

    def test_dang_url_day_du(self):
        proxy = parse_proxy("http://tai-khoan:mat-khau@1.2.3.4:8080")
        self.assertEqual((proxy.host, proxy.port), ("1.2.3.4", 8080))
        self.assertEqual((proxy.username, proxy.password), ("tai-khoan", "mat-khau"))

    def test_dang_thieu_scheme_co_tai_khoan(self):
        proxy = parse_proxy("tai-khoan:mat-khau@1.2.3.4:3128")
        self.assertEqual(proxy.scheme, "http")
        self.assertEqual(proxy.username, "tai-khoan")

    def test_dang_khong_co_tai_khoan(self):
        proxy = parse_proxy("1.2.3.4:8080")
        self.assertEqual((proxy.host, proxy.port), ("1.2.3.4", 8080))
        self.assertEqual(proxy.username, "")
        self.assertEqual(proxy.secrets(), ())

    def test_mat_khau_co_dau_hai_cham(self):
        proxy = parse_proxy("1.2.3.4:8080:tai-khoan:mat:khau:la")
        self.assertEqual(proxy.password, "mat:khau:la")

    def test_tai_khoan_da_encode_duoc_giai_ma_va_encode_lai(self):
        proxy = parse_proxy("http://tai%40khoan:mat%2Fkhau@1.2.3.4:8080")
        self.assertEqual(proxy.username, "tai@khoan")
        self.assertEqual(proxy.password, "mat/khau")
        self.assertEqual(proxy.url, "http://tai%40khoan:mat%2Fkhau@1.2.3.4:8080")

    def test_ky_tu_dac_biet_trong_dang_bon_truong(self):
        proxy = parse_proxy("1.2.3.4:8080:u:p@ss:w/rd")
        self.assertEqual(proxy.password, "p@ss:w/rd")
        self.assertIn("p%40ss%3Aw%2Frd", proxy.url)

    def test_de_trong_thi_tra_none(self):
        self.assertIsNone(parse_proxy(""))
        self.assertIsNone(parse_proxy("   "))
        self.assertIsNone(parse_proxy(None))

    def test_bo_khoang_trang(self):
        self.assertEqual(parse_proxy("  1.2.3.4:8080  ").port, 8080)

    def test_thieu_port_thi_dung_mac_dinh_theo_scheme(self):
        self.assertEqual(parse_proxy("http://1.2.3.4").port, 8080)
        if _has_pysocks():
            self.assertEqual(parse_proxy("socks5://1.2.3.4").port, 1080)

    def test_cac_chuoi_sai_thi_bao_loi(self):
        for value in ("1.2.3.4", "1.2.3.4:abc", "1.2.3.4:70000", "1.2.3.4:8080:user", "ftp://1.2.3.4:21"):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                parse_proxy(value)

    def test_socks_thieu_pysocks_thi_bao_loi_ro_cach_cai(self):
        if _has_pysocks():
            self.skipTest("đã cài PySocks")
        with self.assertRaises(ConfigError) as error:
            parse_proxy("socks5://1.2.3.4:1080")
        self.assertEqual(str(error.exception), SOCKS_HINT)


class ProxyShapeTests(unittest.TestCase):
    def make(self, **kwargs) -> Proxy:
        values = {"host": "1.2.3.4", "port": 8080, **kwargs}
        return Proxy(**values)

    def test_url_co_tai_khoan(self):
        self.assertEqual(
            self.make(username="u", password="p").url, "http://u:p@1.2.3.4:8080"
        )

    def test_url_khong_tai_khoan(self):
        self.assertEqual(self.make().url, "http://1.2.3.4:8080")

    def test_nhan_dang_khong_lo_mat_khau(self):
        label = self.make(username="u", password="bi-mat").label
        self.assertIn("1.2.3.4:8080", label)
        self.assertNotIn("bi-mat", label)
        self.assertNotIn("u:", label)

    def test_danh_sach_can_che_gom_mat_khau_va_url(self):
        secrets = self.make(username="u", password="bi-mat").secrets()
        self.assertIn("bi-mat", secrets)
        self.assertIn("u:bi-mat", secrets)
        self.assertIn("http://u:bi-mat@1.2.3.4:8080", secrets)

    def test_chuoi_dai_duoc_che_truoc_de_khong_lo_tai_khoan(self):
        proxy = self.make(username="tai-khoan", password="bi-mat")
        secrets = proxy.secrets()
        self.assertEqual(secrets, tuple(sorted(secrets, key=len, reverse=True)))

        # Thông báo lỗi của requests chứa cả URL proxy: tài khoản cũng phải bị che,
        # không chỉ mật khẩu, nếu không thì lộ một nửa thông tin.
        message = f"ProxyError {proxy.url} khi kết nối"
        masked = mask_secrets(message, secrets)
        self.assertNotIn("tai-khoan", masked)
        self.assertNotIn("bi-mat", masked)

    def test_dung_cho_ca_http_va_https(self):
        self.assertEqual(
            self.make().proxies(),
            {"http": "http://1.2.3.4:8080", "https": "http://1.2.3.4:8080"},
        )


class ProxyServerTestCase(unittest.TestCase):
    """Dựng một HTTP proxy thật để chứng minh request đi qua nó."""

    def start_proxy(self):
        received: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append({"path": self.path, "headers": dict(self.headers)})
                body = b"qua proxy"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # giữ output test sạch
                return None

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        # Cleanup chạy LIFO: shutdown() trước rồi mới đóng socket lắng nghe.
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, received

    def test_request_di_qua_proxy_va_khong_can_dns_may_chu_dich(self):
        server, received = self.start_proxy()
        client = HttpClient(
            base_url="http://may-chu-khong-ton-tai.test/tthc",
            proxy=Proxy(host="127.0.0.1", port=server.server_port),
            retries=1,
        )
        self.addCleanup(client.close)

        response = client.get("/tchs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "qua proxy")
        # Proxy nhận URL tuyệt đối: đúng đường đi của một HTTP proxy.
        self.assertEqual(received[0]["path"], "http://may-chu-khong-ton-tai.test/tthc/tchs")

    def test_gui_tai_khoan_proxy_bang_proxy_authorization(self):
        server, received = self.start_proxy()
        client = HttpClient(
            base_url="http://may-chu-khong-ton-tai.test/tthc",
            proxy=Proxy(host="127.0.0.1", port=server.server_port, username="u", password="bi-mat"),
            retries=1,
        )
        self.addCleanup(client.close)

        client.get("/tchs")

        self.assertIn("Proxy-Authorization", received[0]["headers"])

    def test_khong_dung_proxy_thi_khong_goi_qua_proxy(self):
        server, received = self.start_proxy()
        client = HttpClient(
            base_url=f"http://127.0.0.1:{server.server_port}/tthc",
            retries=1,
        )
        self.addCleanup(client.close)
        client.get("/tchs")
        # Không có proxy thì request tới thẳng đích, đường dẫn không phải URL tuyệt đối.
        self.assertEqual(received[0]["path"], "/tthc/tchs")


class ProxyErrorTests(unittest.TestCase):
    def test_loi_proxy_duoc_doi_thanh_network_error_da_che(self):
        # Port không có gì lắng nghe → requests ném ProxyError.
        client = HttpClient(
            base_url="http://may-chu.test/tthc",
            proxy=Proxy(host="127.0.0.1", port=1, username="u", password="bi-mat-proxy"),
            retries=1,
            timeout=2,
        )
        self.addCleanup(client.close)

        with self.assertRaises(NetworkError) as error:
            client.get("/tchs")

        message = str(error.exception)
        self.assertNotIn("bi-mat-proxy", message)
        self.assertNotIn("u:bi-mat-proxy", message)
        self.assertIn("proxy 127.0.0.1:1", message)

    def test_loi_mang_thuong_cung_duoc_boc(self):
        client = HttpClient(base_url="http://may-chu-khong-ton-tai.test/tthc", retries=1, timeout=2)
        self.addCleanup(client.close)
        with self.assertRaises(NetworkError):
            client.get("/tchs")


if __name__ == "__main__":
    unittest.main()
