import sys
import unittest

from gdt_tax.captcha import (
    CaptchaSolver,
    available_solvers,
    create_solver,
    normalize_text,
    register_plugins,
    register_solver,
)
from gdt_tax.errors import CaptchaError


class DummySolver(CaptchaSolver):
    name = "dummy"

    def solve(self, image: bytes) -> str:
        return "dummy-code"


class RegistryTests(unittest.TestCase):
    def test_co_san_cac_solver_mac_dinh(self):
        names = available_solvers()
        for expected in ("ddddocr", "easyocr", "paddleocr", "manual", "remote"):
            self.assertIn(expected, names)

    def test_tao_solver_manual_khong_can_easyocr(self):
        solver = create_solver("manual")
        self.assertEqual(solver.name, "manual")
        # Chọn solver khác không được kéo theo thư viện OCR nặng.
        self.assertNotIn("gdt_tax.captcha.easyocr_solver", sys.modules)

    def test_solver_khong_ton_tai(self):
        with self.assertRaises(CaptchaError):
            create_solver("khong-co-solver-nay")

    def test_duong_dan_module_sai(self):
        with self.assertRaises(CaptchaError):
            create_solver("khong.ton.tai:Solver")

    def test_module_khong_co_lop_do(self):
        with self.assertRaises(CaptchaError):
            create_solver("gdt_tax.captcha.base:KhongCoLopNay")

    def test_lop_khong_ke_thua_captcha_solver(self):
        with self.assertRaises(CaptchaError):
            create_solver("gdt_tax.models:CaseRecord")

    def test_solver_remote_thieu_url(self):
        with self.assertRaises(CaptchaError):
            create_solver("remote")

    def test_solver_remote_tao_duoc_khi_co_url(self):
        solver = create_solver("remote", url="https://example.com/solve")
        self.assertEqual(solver.name, "remote")


class NormalizeTextTests(unittest.TestCase):
    def test_bo_ky_tu_khong_phai_chu_so(self):
        self.assertEqual(normalize_text(" a1 b2 "), "a1b2")
        self.assertEqual(normalize_text("tnav 6"), "tnav6")

    def test_bo_ca_chu_co_dau_tieng_viet(self):
        # str.isalnum() coi chữ có dấu là hợp lệ, còn CAPTCHA thì không.
        self.assertEqual(normalize_text("hoá"), "ho")

    def test_rong_thi_tra_rong(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")


class RegistrationTests(unittest.TestCase):
    def test_dang_ky_bang_code(self):
        register_solver("dummy", f"{__name__}:DummySolver")
        self.assertIn("dummy", available_solvers())
        self.assertEqual(create_solver("dummy").solve(b"anh"), "dummy-code")

    def test_dang_ky_bang_chuoi_plugin(self):
        register_plugins(f"dummy-plugin={__name__}:DummySolver")
        self.assertIn("dummy-plugin", available_solvers())

    def test_dang_ky_khong_hop_le(self):
        with self.assertRaises(CaptchaError):
            register_solver("thieu-duong-dan", "khong-co-dau-hai-cham")

    def test_dung_truc_tiep_duong_dan_module(self):
        solver = create_solver(f"{__name__}:DummySolver")
        self.assertEqual(solver.solve(b"anh"), "dummy-code")


if __name__ == "__main__":
    unittest.main()
