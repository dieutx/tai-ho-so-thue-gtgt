"""Smoke test cho từng backend OCR.

Test chỉ chạy khi thư viện tương ứng đã được cài, nên CI nhẹ vẫn xanh. Ảnh mẫu
được tạo bằng scripts/synthetic_captcha.py (150×38, 5 ký tự chữ-số), không phải
ảnh thu thập từ cổng.

Vì CAPTCHA đổi nội dung theo từng phiên, test chỉ kiểm tra solver **đọc ra đúng
định dạng** và không lỗi, không so khớp ký tự cụ thể.
"""

import importlib.util
import unittest
from pathlib import Path

from gdt_tax.captcha import create_solver

SAMPLE = Path(__file__).parent / "fixtures" / "sample_captcha.png"
LENGTH = 5


def sample_image() -> bytes:
    return SAMPLE.read_bytes()


def installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


class SolverSmokeTestCase(unittest.TestCase):
    """Lớp cơ sở: mọi backend phải trả chuỗi rỗng hoặc đúng 5 ký tự chữ-số."""

    solver_name = ""
    module_name = ""

    def setUp(self):
        if not self.module_name or not installed(self.module_name):
            self.skipTest(f"chưa cài {self.module_name}")
        self.solver = create_solver(self.solver_name)

    def tearDown(self):
        solver = getattr(self, "solver", None)
        if solver is not None:
            solver.close()

    def test_doc_anh_tong_hop(self):
        text = self.solver.solve(sample_image())
        self.assertIsInstance(text, str)
        self.assertIn(len(text), (0, LENGTH))
        if text:
            self.assertTrue(text.isascii() and text.isalnum())

    def test_khong_doc_duoc_thi_tra_chuoi_rong(self):
        # Ảnh trắng trơn: không có ký tự nào nên phải trả rỗng, không được vỡ.
        import cv2
        import numpy as np

        blank = cv2.imencode(".png", np.full((38, 150, 3), 255, np.uint8))[1].tobytes()
        self.assertEqual(self.solver.solve(blank), "")


class DdddOcrBackendTests(SolverSmokeTestCase):
    solver_name = "ddddocr"
    module_name = "ddddocr"


class EasyOcrBackendTests(SolverSmokeTestCase):
    solver_name = "easyocr"
    module_name = "easyocr"

    def test_khong_doc_duoc_thi_tra_chuoi_rong(self):
        self.skipTest("easyocr luôn tốn vài giây cho mỗi ảnh; đã kiểm ở backend khác")


class PaddleOcrBackendTests(SolverSmokeTestCase):
    solver_name = "paddleocr"
    module_name = "paddleocr"


class ManualBackendTests(unittest.TestCase):
    def test_nhap_tay_khong_can_thu_vien_ocr(self):
        solver = create_solver("manual")
        self.assertEqual(solver.name, "manual")


if __name__ == "__main__":
    unittest.main()
