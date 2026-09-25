import unittest
from unittest import mock

from gdt_tax.constants import DEFAULT_HEADERS
from gdt_tax.headers import (
    BROWSER_ORDER,
    DEFAULT_PROFILE,
    IMAGE_ACCEPT,
    MINIMAL_IMAGE_ACCEPT,
    PAGE_ACCEPT,
    PROFILE_BROWSER,
    PROFILE_MINIMAL,
    accept_encoding,
    build_image_headers,
    build_page_headers,
    build_xhr_headers,
    chrome_order,
    client_hints,
    header_names,
    reconcile_client_hints,
)

CHROME_WINDOWS = DEFAULT_HEADERS["User-Agent"]
FIREFOX = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"


class ClientHintsTests(unittest.TestCase):
    def test_tinh_hint_tu_user_agent_chrome(self):
        hints = client_hints(CHROME_WINDOWS)
        self.assertIn('v="153"', hints["sec-ch-ua"])
        self.assertEqual(hints["sec-ch-ua-platform"], '"Windows"')
        self.assertEqual(hints["sec-ch-ua-mobile"], "?0")

    def test_platform_theo_he_dieu_hanh_khac(self):
        mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/153 Safari/537.36"
        linux = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36"
        self.assertEqual(client_hints(mac)["sec-ch-ua-platform"], '"macOS"')
        self.assertEqual(client_hints(linux)["sec-ch-ua-platform"], '"Linux"')

    def test_android_thi_mobile_bang_1(self):
        android = (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
            "Chrome/153 Mobile Safari/537.36"
        )
        self.assertEqual(client_hints(android)["sec-ch-ua-mobile"], "?1")

    def test_khong_phai_chrome_thi_bo_qua(self):
        self.assertEqual(client_hints(FIREFOX), {})
        self.assertEqual(client_hints(""), {})

    def test_chrome_nhung_khong_ro_he_dieu_hanh_thi_bo_qua(self):
        self.assertEqual(client_hints("Mozilla/5.0 Chrome/153 Safari/537.36"), {})


class ReconcileClientHintsTests(unittest.TestCase):
    def test_khong_co_hint_thi_giu_nguyen(self):
        headers = {"User-Agent": FIREFOX, "Accept-Language": "vi"}
        self.assertEqual(reconcile_client_hints(headers), headers)

    def test_doi_user_agent_sang_trinh_duyet_khac_thi_bo_hint(self):
        headers = {"User-Agent": FIREFOX, **{name: "cu" for name in
                   ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform")}}
        self.assertNotIn("sec-ch-ua", reconcile_client_hints(headers))

    def test_doi_user_agent_sang_chrome_linux_thi_hint_cap_nhat(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
            "sec-ch-ua-platform": '"Windows"',
        }
        self.assertEqual(reconcile_client_hints(headers)["sec-ch-ua-platform"], '"Linux"')

    def test_nhan_dien_ten_header_khong_phan_biet_hoa_thuong(self):
        headers = {"user-agent": CHROME_WINDOWS, "Sec-CH-UA": "cu"}
        result = reconcile_client_hints(headers)
        self.assertNotIn("Sec-CH-UA", result)
        self.assertEqual(result["user-agent"], CHROME_WINDOWS)
        self.assertIn("sec-ch-ua", result)


class PageHeadersTests(unittest.TestCase):
    def test_profile_minimal_giu_nguyen_bo_header_cu(self):
        headers = build_page_headers(
            profile=PROFILE_MINIMAL, headers={"Referer": "https://x.test/tthc/login"}
        )
        self.assertEqual(
            headers,
            {**DEFAULT_HEADERS, "Referer": "https://x.test/tthc/login"},
        )
        self.assertNotIn("Sec-Fetch-Dest", headers)

    def test_profile_browser_them_sec_fetch_va_accept_trang(self):
        headers = build_page_headers(profile=PROFILE_BROWSER, site="none")
        self.assertEqual(headers["Accept"], PAGE_ACCEPT)
        self.assertEqual(headers["Sec-Fetch-Site"], "none")
        self.assertEqual(headers["Sec-Fetch-Mode"], "navigate")
        self.assertEqual(headers["Sec-Fetch-Dest"], "document")
        self.assertEqual(headers["Sec-Fetch-User"], "?1")
        self.assertEqual(headers["Upgrade-Insecure-Requests"], "1")
        self.assertEqual(headers["sec-ch-ua-platform"], '"Windows"')

    def test_accept_rieng_khong_bi_ghi_de(self):
        headers = build_page_headers(profile=PROFILE_BROWSER, headers={"Accept": "text/html"})
        self.assertEqual(headers["Accept"], "text/html")

    def test_user_agent_ghi_de_thi_bo_hint(self):
        headers = build_page_headers(profile=PROFILE_BROWSER, headers={"User-Agent": FIREFOX})
        self.assertEqual(headers["User-Agent"], FIREFOX)
        self.assertNotIn("sec-ch-ua", headers)

    def test_dieu_huong_dau_tien_khong_gui_referer(self):
        # Sec-Fetch-Site: none nghĩa là chưa có trang nguồn, gửi Referer là mâu thuẫn.
        headers = build_page_headers(
            profile=PROFILE_BROWSER, site="none", headers={"Referer": "https://x.test/"}
        )
        self.assertNotIn("Referer", headers)
        self.assertEqual(headers["Sec-Fetch-Site"], "none")

    def test_dieu_huong_trong_cung_trang_thi_giu_referer(self):
        headers = build_page_headers(profile=PROFILE_BROWSER, headers={"Referer": "https://x.test/tthc/tchs"})
        self.assertEqual(headers["Referer"], "https://x.test/tthc/tchs")

    def test_minimal_van_gui_referer_nhu_cu(self):
        headers = build_page_headers(profile=PROFILE_MINIMAL, site="none", headers={"Referer": "https://x.test/"})
        self.assertEqual(headers["Referer"], "https://x.test/")


class XhrHeadersTests(unittest.TestCase):
    def test_profile_minimal_giu_nguyen_bo_header_cu(self):
        headers = build_xhr_headers(
            profile=PROFILE_MINIMAL, accept="text/html-partial", headers={"HX-Request": "true"}
        )
        self.assertEqual(
            headers,
            {**DEFAULT_HEADERS, "Accept": "text/html-partial", "HX-Request": "true"},
        )
        self.assertNotIn("Sec-Fetch-Dest", headers)

    def test_profile_browser_dung_dest_empty_va_mode_cors(self):
        headers = build_xhr_headers(profile=PROFILE_BROWSER)
        self.assertEqual(headers["Accept"], "*/*")
        self.assertEqual(headers["Sec-Fetch-Dest"], "empty")
        self.assertEqual(headers["Sec-Fetch-Mode"], "cors")
        self.assertEqual(headers["Sec-Fetch-Site"], "same-origin")
        self.assertNotIn("Sec-Fetch-User", headers)
        self.assertNotIn("Upgrade-Insecure-Requests", headers)

    def test_accept_htmx_duoc_giu(self):
        headers = build_xhr_headers(profile=PROFILE_BROWSER, accept="text/html-partial")
        self.assertEqual(headers["Accept"], "text/html-partial")


class ImageHeadersTests(unittest.TestCase):
    def test_accept_anh_theo_profile(self):
        self.assertEqual(build_image_headers(profile=PROFILE_MINIMAL)["Accept"], MINIMAL_IMAGE_ACCEPT)
        self.assertEqual(build_image_headers(profile=PROFILE_BROWSER)["Accept"], IMAGE_ACCEPT)

    def test_profile_browser_dung_dest_image(self):
        headers = build_image_headers(profile=PROFILE_BROWSER, headers={"Referer": "https://x.test"})
        self.assertEqual(headers["Sec-Fetch-Dest"], "image")
        self.assertEqual(headers["Sec-Fetch-Mode"], "no-cors")
        self.assertEqual(headers["Referer"], "https://x.test")
        self.assertNotIn("Upgrade-Insecure-Requests", headers)


class HeaderNamesTests(unittest.TestCase):
    def test_chi_in_ten_khong_in_gia_tri(self):
        names = header_names({"X-Token": "bi-mat", "Referer": "https://x.test"})
        self.assertEqual(names, "Referer, X-Token")
        self.assertEqual(header_names(None), "")


class ProfileNameTests(unittest.TestCase):
    def test_minimal_khong_bao_gio_gui_dau_hieu_browser(self):
        for builder in (build_page_headers, build_xhr_headers, build_image_headers):
            headers = builder(profile=PROFILE_MINIMAL)
            self.assertNotIn("Sec-Fetch-Dest", headers)
            self.assertNotIn("Accept-Encoding", headers)

    def test_browser_la_mac_dinh(self):
        self.assertEqual(DEFAULT_PROFILE, PROFILE_BROWSER)
        for builder in (build_page_headers, build_xhr_headers, build_image_headers):
            self.assertIn("Sec-Fetch-Dest", builder())


def _fake_modules(available: set[str]):
    """Giả lập môi trường có/không có thư viện giải nén."""
    return mock.patch(
        "gdt_tax.headers._has_module", side_effect=lambda name: name in available
    )


class AcceptEncodingTests(unittest.TestCase):
    def tearDown(self):
        accept_encoding.cache_clear()

    def test_chi_gom_codec_giai_nen_duoc(self):
        with _fake_modules({"gzip", "deflate"}):
            accept_encoding.cache_clear()
            self.assertEqual(accept_encoding(), "gzip, deflate")

    def test_co_brotli_thi_them_br(self):
        with _fake_modules({"brotli"}):
            accept_encoding.cache_clear()
            self.assertEqual(accept_encoding(), "gzip, deflate, br")

    def test_khong_bao_gio_khai_zstd(self):
        # urllib3 chỉ giải mã gzip/deflate/br/x-gzip: khai zstd là ZIP hỏng.
        with _fake_modules({"zstandard", "brotli", "brotlicffi"}):
            accept_encoding.cache_clear()
            self.assertNotIn("zstd", accept_encoding())
            self.assertEqual(accept_encoding(), "gzip, deflate, br")

    def test_browser_gui_kem_accept_encoding(self):
        with _fake_modules({"brotli"}):
            accept_encoding.cache_clear()
            headers = build_xhr_headers(profile=PROFILE_BROWSER)
        self.assertEqual(headers["Accept-Encoding"], "gzip, deflate, br")


class ChromeOrderTests(unittest.TestCase):
    def test_sec_fetch_dat_dung_vi_tri_nhu_chrome(self):
        headers = build_page_headers(profile=PROFILE_BROWSER, headers={"Referer": "https://x.test"})
        order = list(headers)
        self.assertLess(order.index("sec-ch-ua"), order.index("User-Agent"))
        self.assertLess(order.index("User-Agent"), order.index("Accept"))
        self.assertLess(order.index("Accept"), order.index("Sec-Fetch-Site"))
        self.assertLess(order.index("Sec-Fetch-Dest"), order.index("Referer"))
        self.assertLess(order.index("Referer"), order.index("Accept-Encoding"))
        self.assertLess(order.index("Accept-Encoding"), order.index("Accept-Language"))

    def test_header_la_giu_nguyen_thu_tu(self):
        ordered = chrome_order({"HX-Request": "true", "User-Agent": "ua"})
        self.assertEqual(list(ordered), ["User-Agent", "HX-Request"])

    def test_khop_ten_header_khong_phan_biet_hoa_thuong(self):
        ordered = chrome_order({"X-Token": "1", "user-agent": "ua"})
        self.assertEqual(list(ordered), ["user-agent", "X-Token"])

    def test_moi_header_deu_duoc_giu(self):
        source = {name: "x" for name in BROWSER_ORDER}
        source["X-Token"] = "y"
        self.assertEqual(set(chrome_order(source)), set(source))


if __name__ == "__main__":
    unittest.main()
