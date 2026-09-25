import unittest

from gdt_tax.models import CaseRecord
from gdt_tax.naming import UNKNOWN, safe_filename_part, zip_filename


class SafeFilenamePartTests(unittest.TestCase):
    def test_bo_dau_tieng_viet(self):
        self.assertEqual(safe_filename_part("Hoạt động"), "Hoat-dong")

    def test_chu_dj_thanh_d(self):
        self.assertEqual(
            safe_filename_part("hóa đơn điện tử đã lập sai"), "hoa-don-dien-tu-da-lap-sai"
        )
        self.assertEqual(safe_filename_part("Đã nộp"), "Da-nop")

    def test_ky_tu_dac_biet_thanh_dau_gach(self):
        self.assertEqual(safe_filename_part("a/b:c*d?"), "a-b-c-d")

    def test_cat_bot_khoang_trang_va_dau_o_hai_dau(self):
        self.assertEqual(safe_filename_part("  ...Tờ khai...  "), "To-khai")

    def test_gia_tri_rong_dung_mac_dinh(self):
        self.assertEqual(safe_filename_part(""), UNKNOWN)
        self.assertEqual(safe_filename_part(None), UNKNOWN)

    def test_gioi_han_do_dai(self):
        self.assertEqual(len(safe_filename_part("x" * 200, 10)), 10)


class ZipFilenameTests(unittest.TestCase):
    def make_record(self) -> CaseRecord:
        return CaseRecord(
            ma_ho_so="11320250292469209",
            nguon="ETAX",
            to_khai="TỜ KHAI THUẾ GIÁ TRỊ GIA TĂNG",
            ky_tinh_thue="12/2024",
            loai_to_khai="Chính thức",
        )

    def test_ten_file_du_bon_phan(self):
        self.assertEqual(
            zip_filename(self.make_record()),
            "11320250292469209__12-2024__Chinh-thuc__TO-KHAI-THUE-GIA-TRI-GIA-TANG.zip",
        )

    def test_thieu_ky_tinh_thue_dung_placeholder(self):
        record = self.make_record()
        record.ky_tinh_thue = ""
        self.assertIn(f"__{UNKNOWN}__", zip_filename(record))


if __name__ == "__main__":
    unittest.main()
