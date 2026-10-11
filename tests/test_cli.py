import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from gdt_tax.captcha import available_solvers
from gdt_tax.cli import (
    build_parser,
    log_secrets,
    main,
    parse_headers,
    parse_solver_options,
)
from gdt_tax.headers import PROFILES
from gdt_tax.proxy import parse_proxy


class ParseSolverOptionsTests(unittest.TestCase):
    def test_gia_tri_json_duoc_chuyen_kieu(self):
        options = parse_solver_options(
            ["timeout=15", "url=https://example.com/solve", "gpu=true"]
        )
        self.assertEqual(
            options, {"timeout": 15, "url": "https://example.com/solve", "gpu": True}
        )

    def test_gia_tri_khong_phai_json_giu_nguyen_chuoi(self):
        self.assertEqual(parse_solver_options(["prompt=Nhap ma CAPTCHA?"]), {"prompt": "Nhap ma CAPTCHA?"})

    def test_bo_qua_muc_rong(self):
        self.assertEqual(parse_solver_options(["", "  ", "=khong-co-ten"]), {})

    def test_danh_sach_rong(self):
        self.assertEqual(parse_solver_options(None), {})


class ParseHeadersTests(unittest.TestCase):
    def test_doc_header_kieu_dau_bang(self):
        self.assertEqual(parse_headers(["X-Token=abc"]), {"X-Token": "abc"})

    def test_doc_header_kieu_hai_cham(self):
        self.assertEqual(parse_headers(["User-Agent: Mozilla/5.0"]), {"User-Agent": "Mozilla/5.0"})

    def test_giu_nguyen_gia_tri_co_dau_hai_cham(self):
        headers = parse_headers(["Referer: https://dichvucong.gdt.gov.vn/tthc/tchs"])
        self.assertEqual(headers["Referer"], "https://dichvucong.gdt.gov.vn/tthc/tchs")

    def test_bo_qua_muc_khong_co_ten(self):
        self.assertEqual(parse_headers(["", "  ", "=abc", ":abc", "khong-co-dau"]), {})

    def test_nhieu_header_va_lan_sau_thang(self):
        headers = parse_headers(["X-A=1", "X-B=2", "X-A=3"])
        self.assertEqual(headers, {"X-A": "3", "X-B": "2"})

    def test_danh_sach_rong(self):
        self.assertEqual(parse_headers(None), {})


class ParserTests(unittest.TestCase):
    def test_help_utf8_khi_console_mac_dinh_cp1252(self):
        for module in (
            "gdt_tax", "gdt_tax.gnt", "gdt_tax.tb", "gdt_tax.inventory",
            "gdt_tax.parser.cli", "gdt_tax.classify", "gdt_tax.export",
        ):
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-m", module, "--help"],
                    env={**os.environ, "PYTHONIOENCODING": "cp1252"},
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True, timeout=30, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
                output = result.stdout.decode("utf-8")
                self.assertIn("usage:", output)
                self.assertTrue(any(ord(char) > 127 for char in output))

    def test_co_bat_tat_dvc_va_mac_dinh_khong_ghi_de_env(self):
        parser = build_parser()
        self.assertIsNone(parser.parse_args([]).dvc_enabled)
        self.assertTrue(parser.parse_args(["--enable-dvc"]).dvc_enabled)
        self.assertFalse(parser.parse_args(["--disable-dvc"]).dvc_enabled)
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            parser.parse_args(["--enable-dvc", "--disable-dvc"])

    def test_gia_tri_mac_dinh(self):
        args = build_parser().parse_args([])
        self.assertIsNone(args.from_date)
        self.assertIsNone(args.to_date)
        self.assertIsNone(args.case_id)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.env_file, ".env")
        self.assertEqual(args.solver_option, [])
        self.assertEqual(args.header, [])
        self.assertIsNone(args.log_file)
        self.assertIsNone(args.dump_http)
        self.assertIsNone(args.header_profile)

    def test_doc_tham_so_day_du(self):
        args = build_parser().parse_args(
            [
                "--from-date",
                "01/01/2025",
                "--to-date",
                "31/01/2025",
                "--case-id",
                "ABC-1",
                "--output-dir",
                "download/2025-01",
                "--solver",
                "manual",
                "--dry-run",
                "-v",
            ]
        )
        self.assertEqual(args.from_date, "01/01/2025")
        self.assertEqual(args.output_dir, "download/2025-01")
        self.assertEqual(args.solver, "manual")
        self.assertTrue(args.dry_run)
        self.assertTrue(args.verbose)

    def test_doc_tham_so_chan_doan(self):
        args = build_parser().parse_args(
            [
                "--header",
                "Referer=https://dichvucong.gdt.gov.vn/tthc/tchs",
                "--header",
                "X-Token: abc",
                "--log-file",
                "logs/run.log",
                "--dump-http",
                "http-dump",
            ]
        )
        self.assertEqual(len(args.header), 2)
        self.assertEqual(args.log_file, "logs/run.log")
        self.assertEqual(args.dump_http, "http-dump")

    def test_doc_header_profile(self):
        args = build_parser().parse_args(["--header-profile", "browser"])
        self.assertEqual(args.header_profile, "browser")

    def test_doc_proxy(self):
        args = build_parser().parse_args(["--proxy", "1.2.3.4:8080:u:p"])
        self.assertEqual(args.proxy, "1.2.3.4:8080:u:p")

    def test_mac_dinh_khong_co_proxy(self):
        self.assertIsNone(build_parser().parse_args([]).proxy)

    def test_header_profile_la_khong_hop_le_thi_bao_loi(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            build_parser().parse_args(["--header-profile", "chrome"])

    def test_danh_sach_chon_header_profile_lay_tu_headers(self):
        action = next(
            action
            for action in build_parser()._actions
            if action.dest == "header_profile"
        )
        self.assertEqual(list(action.choices), list(PROFILES))

    def test_co_tham_so_phien_ban(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--version"])


class LogSecretsTests(unittest.TestCase):
    def settings(self, password: str):
        return mock.Mock(password=password)

    def test_gom_ca_mat_khau_proxy_va_mat_khau_tai_khoan(self):
        secrets = log_secrets(
            self.settings("mat-khau-cong"), parse_proxy("1.2.3.4:8080:u:mat-khau-proxy")
        )
        self.assertIn("mat-khau-cong", secrets)
        self.assertIn("mat-khau-proxy", secrets)

    def test_khong_co_proxy_thi_chi_che_mat_khau_tai_khoan(self):
        self.assertEqual(log_secrets(self.settings("mat-khau-cong"), None), ("mat-khau-cong",))

    def test_khong_co_mat_khau_thi_chi_che_proxy(self):
        secrets = log_secrets(self.settings(""), parse_proxy("1.2.3.4:8080:u:mat-khau-proxy"))
        self.assertIn("mat-khau-proxy", secrets)
        self.assertNotIn("", secrets)


class MainTests(unittest.TestCase):
    def test_khoang_dvc_tam_tat_khong_nap_solver_hoac_goi_http(self):
        env = {"GDT_USERNAME": "test", "GDT_PASSWORD": "secret", "GDT_FROM_DATE": "01/07/2025",
               "GDT_TO_DATE": "31/07/2025"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("gdt_tax.cli.create_solver") as solver:
            with mock.patch("gdt_tax.cli.HttpClient") as http, redirect_stdout(io.StringIO()):
                code = main(["--env-file", "missing.env"])
        self.assertEqual(code, 1)
        solver.assert_not_called()
        http.assert_not_called()

    def test_liet_ke_solver(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--list-solvers"])
        self.assertEqual(code, 0)
        self.assertEqual(buffer.getvalue().split(), list(available_solvers()))

    def test_liet_ke_solver_tao_duoc_file_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logs" / "run.log"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["--list-solvers", "--log-file", str(path)])
            self.assertEqual(code, 0)
            self.assertTrue(path.is_file())

    def test_file_log_khong_mo_duoc_tra_ve_ma_loi_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["--list-solvers", "--log-file", tmp])
        self.assertEqual(code, 2)
        self.assertIn("LỖI CẤU HÌNH", stderr.getvalue())

    def test_proxy_sai_tra_ve_ma_loi_2_truoc_khi_goi_mang(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        env = {"GDT_USERNAME": "synthetic-taxpayer-QL", "GDT_PASSWORD": "mat-khau"}
        with mock.patch.dict(os.environ, env, clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["--proxy", "1.2.3.4", "--env-file", "khong-co.env"])
        self.assertEqual(code, 2)
        self.assertIn("LỖI CẤU HÌNH", stderr.getvalue())

    def test_thieu_cau_hinh_tra_ve_ma_loi_2(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(
                    [
                        "--from-date",
                        "01/01/2025",
                        "--to-date",
                        "31/01/2025",
                        "--env-file",
                        "file-khong-ton-tai.env",
                    ]
                )
        self.assertEqual(code, 2)
        self.assertIn("LỖI CẤU HÌNH", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
