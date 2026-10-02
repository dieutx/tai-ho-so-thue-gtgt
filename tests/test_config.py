import tempfile
import unittest
from datetime import date
from pathlib import Path

from gdt_tax.config import Settings, load_env_file
from gdt_tax.constants import SOURCE_ETAX
from gdt_tax.errors import ConfigError
from gdt_tax.headers import PROFILE_BROWSER, PROFILE_MINIMAL

BASE_ENV = {
    "GDT_USERNAME": "0101234567-QL",
    "GDT_PASSWORD": "mat-khau",
}


class LoadEnvFileTests(unittest.TestCase):
    def test_doc_bien_va_bo_qua_chu_thich(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# ghi chu\n\nGDT_USERNAME=\"tai-khoan\"\nGDT_PASSWORD=bi-mat\n",
                encoding="utf-8",
            )
            values = load_env_file(path)
        self.assertEqual(values, {"GDT_USERNAME": "tai-khoan", "GDT_PASSWORD": "bi-mat"})

    def test_thieu_file_thi_tra_rong(self):
        self.assertEqual(load_env_file("file-khong-ton-tai.env"), {})


class SettingsFromEnvTests(unittest.TestCase):
    def test_gia_tri_mac_dinh(self):
        settings = Settings.from_env(BASE_ENV, env_file=None)
        self.assertEqual(settings.from_date, date(2026, 9, 1))
        self.assertEqual(settings.to_date, date(2026, 9, 25))
        self.assertEqual(settings.download_dir, Path("download"))
        self.assertEqual(settings.captcha_solver, "ddddocr")
        self.assertEqual(settings.page_size, 10)
        self.assertEqual(settings.max_days_per_search, 31)
        self.assertTrue(settings.legacy_etax)

    def test_co_the_tat_legacy_khi_dvc_da_dong_bo(self):
        settings = Settings.from_env(
            {**BASE_ENV, "GDT_LEGACY_ETAX": "false"}, env_file=None
        )
        self.assertFalse(settings.legacy_etax)

    def test_doc_du_bien_moi_truong(self):
        env = {
            **BASE_ENV,
            "GDT_FROM_DATE": "01/01/2025",
            "GDT_TO_DATE": "31/01/2025",
            "GDT_DOWNLOAD_DIR": "download/2025-01",
            "GDT_CASE_ID": "11320250292469209",
            "GDT_CAPTCHA_SOLVER": "manual",
            "GDT_PAGE_SIZE": "20",
            "GDT_DRY_RUN": "true",
        }
        settings = Settings.from_env(env, env_file=None)
        self.assertEqual(settings.from_date, date(2025, 1, 1))
        self.assertEqual(settings.download_dir, Path("download/2025-01"))
        self.assertEqual(settings.case_id, "11320250292469209")
        self.assertEqual(settings.captcha_solver, "manual")
        self.assertEqual(settings.page_size, 20)
        self.assertTrue(settings.dry_run)

    def test_thieu_tai_khoan_thi_bao_loi(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({"GDT_FROM_DATE": "01/01/2025"}, env_file=None)

    def test_bien_moi_truong_thang_file_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "GDT_USERNAME=tu-file\nGDT_PASSWORD=mat-khau-file\n", encoding="utf-8"
            )
            settings = Settings.from_env({"GDT_USERNAME": "tu-moi-truong"}, env_file=path)
        self.assertEqual(settings.username, "tu-moi-truong")
        self.assertEqual(settings.password, "mat-khau-file")

    def test_tham_so_dong_lenh_thang_tat_ca(self):
        env = {**BASE_ENV, "GDT_FROM_DATE": "01/01/2025", "GDT_DRY_RUN": "false"}
        settings = Settings.from_env(env, env_file=None, from_date="01/02/2025", dry_run=True)
        self.assertEqual(settings.from_date, date(2025, 2, 1))
        self.assertTrue(settings.dry_run)

    def test_doc_captcha_options_json(self):
        env = {
            **BASE_ENV,
            "GDT_CAPTCHA_SOLVER": "remote",
            "GDT_CAPTCHA_OPTIONS": '{"url": "https://example.com/solve", "timeout": 10}',
        }
        settings = Settings.from_env(env, env_file=None)
        self.assertEqual(settings.captcha_options["url"], "https://example.com/solve")
        self.assertEqual(settings.captcha_options["timeout"], 10)

    def test_json_sai_thi_bao_loi(self):
        env = {**BASE_ENV, "GDT_CAPTCHA_OPTIONS": "{khong-phai-json}"}
        with self.assertRaises(ConfigError):
            Settings.from_env(env, env_file=None)

    def test_mac_dinh_khong_co_header_log_hay_dump(self):
        settings = Settings.from_env(BASE_ENV, env_file=None)
        self.assertEqual(settings.extra_headers, {})
        self.assertEqual(settings.log_file, "")
        self.assertEqual(settings.http_dump_dir, "")

    def test_doc_header_ghi_de_tu_json(self):
        env = {
            **BASE_ENV,
            "GDT_EXTRA_HEADERS": '{"User-Agent": "Mozilla/5.0", "X-Token": "abc"}',
        }
        settings = Settings.from_env(env, env_file=None)
        self.assertEqual(settings.extra_headers["X-Token"], "abc")

    def test_header_sai_dinh_dang_thi_bao_loi(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({**BASE_ENV, "GDT_EXTRA_HEADERS": "khong-phai-json"}, env_file=None)

    def test_header_rong_thi_bao_loi(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({**BASE_ENV, "GDT_EXTRA_HEADERS": '{"": "x"}'}, env_file=None)

    def test_mac_dinh_header_profile_la_browser(self):
        settings = Settings.from_env(BASE_ENV, env_file=None)
        self.assertEqual(settings.header_profile, PROFILE_BROWSER)

    def test_tat_header_profile_bang_minimal(self):
        settings = Settings.from_env({**BASE_ENV, "GDT_HEADER_PROFILE": "minimal"}, env_file=None)
        self.assertEqual(settings.header_profile, PROFILE_MINIMAL)

    def test_mac_dinh_pause_jitter(self):
        self.assertEqual(Settings.from_env(BASE_ENV, env_file=None).pause_jitter, 0.3)

    def test_doc_pause_jitter(self):
        settings = Settings.from_env({**BASE_ENV, "GDT_PAUSE_JITTER": "0"}, env_file=None)
        self.assertEqual(settings.pause_jitter, 0.0)

    def test_pause_jitter_am_thi_bao_loi(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({**BASE_ENV, "GDT_PAUSE_JITTER": "-1"}, env_file=None)

    def test_doc_header_profile_browser(self):
        settings = Settings.from_env({**BASE_ENV, "GDT_HEADER_PROFILE": "browser"}, env_file=None)
        self.assertEqual(settings.header_profile, PROFILE_BROWSER)

    def test_header_profile_sai_thi_bao_loi(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({**BASE_ENV, "GDT_HEADER_PROFILE": "chrome"}, env_file=None)

    def test_mac_dinh_khong_dung_proxy(self):
        self.assertEqual(Settings.from_env(BASE_ENV, env_file=None).proxy_url, "")

    def test_doc_proxy_tu_moi_truong(self):
        env = {**BASE_ENV, "GDT_PROXY_URL": "1.2.3.4:8080:tai-khoan:mat-khau"}
        settings = Settings.from_env(env, env_file=None)
        self.assertEqual(settings.proxy_url, "1.2.3.4:8080:tai-khoan:mat-khau")

    def test_proxy_sai_thi_bao_loi_ngay(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({**BASE_ENV, "GDT_PROXY_URL": "1.2.3.4"}, env_file=None)

    def test_doc_file_log_va_thu_muc_dump(self):
        env = {**BASE_ENV, "GDT_LOG_FILE": "logs/run.log", "GDT_HTTP_DUMP_DIR": "http-dump"}
        settings = Settings.from_env(env, env_file=None)
        self.assertEqual(settings.log_file, "logs/run.log")
        self.assertEqual(settings.http_dump_dir, "http-dump")

    def test_so_nguyen_sai_thi_bao_loi(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({**BASE_ENV, "GDT_PAGE_SIZE": "muoi"}, env_file=None)

    def test_ngay_sai_dinh_dang_thi_bao_loi(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({**BASE_ENV, "GDT_FROM_DATE": "2025-01-01"}, env_file=None)

    def test_moc_chuyen_nguon_tuy_chinh(self):
        settings = Settings.from_env({**BASE_ENV, "GDT_ETAX_CUTOFF": "01/01/2020"}, env_file=None)
        self.assertEqual(settings.etax_cutoff, date(2020, 1, 1))

    def test_danh_sach_doan_tra_cuu(self):
        env = {**BASE_ENV, "GDT_FROM_DATE": "01/01/2025", "GDT_TO_DATE": "31/01/2025"}
        settings = Settings.from_env(env, env_file=None)
        periods = settings.periods()
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].source, SOURCE_ETAX)


if __name__ == "__main__":
    unittest.main()
