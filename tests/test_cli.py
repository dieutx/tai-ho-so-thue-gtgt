import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from gdt_tax.captcha import available_solvers
from gdt_tax.cli import build_parser, main, parse_solver_options


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


class ParserTests(unittest.TestCase):
    def test_gia_tri_mac_dinh(self):
        args = build_parser().parse_args([])
        self.assertIsNone(args.from_date)
        self.assertIsNone(args.to_date)
        self.assertIsNone(args.case_id)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.env_file, ".env")
        self.assertEqual(args.solver_option, [])

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

    def test_co_tham_so_phien_ban(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["--version"])


class MainTests(unittest.TestCase):
    def test_liet_ke_solver(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["--list-solvers"])
        self.assertEqual(code, 0)
        self.assertEqual(buffer.getvalue().split(), list(available_solvers()))

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
