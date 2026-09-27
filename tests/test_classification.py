import unittest

from gdt_tax.classification import CLASSIFICATION_VERSION, classify_record
from gdt_tax.models import CaseRecord


class ClassificationTests(unittest.TestCase):
    def classify(self, title, procedure=""):
        return classify_record(CaseRecord("test", "ETAX_LEGACY", to_khai=title, ten_tthc=procedure))

    def test_nhan_dien_nhom_va_khong_nham_loai_chinh_thuc_bo_sung(self):
        for title, group in (
            ("01/GTGT - TỜ KHAI THUẾ GIÁ TRỊ GIA TĂNG", "GTGT"),
            ("05/KK-TNCN - Tờ khai thu nhập cá nhân", "TNCN"),
            ("Tờ khai quyết toán thuế thu nhập doanh nghiệp", "TNDN"),
            ("TO KHAI 03/TNDN", "TNDN"),
        ):
            with self.subTest(title=title):
                record = self.classify(title)
                self.assertEqual(record.nhom_to_khai, group)
                self.assertEqual(record.loai_tai_lieu, "DECLARATION")
                self.assertEqual(record.quy_tac_phan_loai, CLASSIFICATION_VERSION)
                self.assertTrue(record.ly_do_phan_loai)
                self.assertEqual(record.loai_to_khai, "")

    def test_thong_bao_va_phu_luc_khong_bi_goi_la_to_khai(self):
        notice = self.classify("Thông báo tiếp nhận tờ khai GTGT")
        self.assertEqual(notice.nhom_to_khai, "GTGT")
        self.assertEqual(notice.loai_tai_lieu, "NOTICE")
        self.assertEqual(self.classify("Phụ lục TNCN").loai_tai_lieu, "APPENDIX")

    def test_thieu_tin_hieu_va_tin_hieu_mau_thuan_giu_unknown(self):
        self.assertEqual(self.classify("").nhom_to_khai, "UNKNOWN")
        self.assertEqual(self.classify("Tờ khai lệ phí môn bài").nhom_to_khai, "OTHER")
        conflict = self.classify("Tờ khai GTGT", "Khai thuế TNCN")
        self.assertEqual(conflict.nhom_to_khai, "UNKNOWN")
        self.assertIn("mâu thuẫn", conflict.ly_do_phan_loai)

    def test_tu_khoa_phai_co_ranh_gioi(self):
        self.assertEqual(self.classify("randomGTGTsuffix").nhom_to_khai, "UNKNOWN")
