import unittest
from datetime import date

import taitokhaiGTGT_fix_v12_full as app


class CoreTests(unittest.TestCase):
    def test_chia_khoang_ngay_va_moc_etax(self):
        periods = list(app.iter_search_periods("15/05/2025", "05/07/2025"))
        self.assertEqual(
            periods,
            [
                (date(2025, 5, 15), date(2025, 6, 14), "ETAX"),
                (date(2025, 6, 15), date(2025, 6, 30), "ETAX"),
                (date(2025, 7, 1), date(2025, 7, 5), "DVC"),
            ],
        )

    def test_doc_bang_etax(self):
        html = """
        <input id="goToPage_tdt" max="3">
        <table><tbody><tr>
          <td>1</td><td>11320250292469209</td>
          <td>TỜ KHAI THUẾ GIÁ TRỊ GIA TĂNG</td><td>12/2024</td>
          <td>Chính thức</td><td>1</td><td>0</td>
          <td>20/01/2025 17:11:35</td><td>Thuế Hà Tĩnh</td>
          <td>Cơ quan thuế chấp nhận hồ sơ</td><td>
            <i data-ma-ho-so="11320250292469209" data-loai="ETAX"></i>
          </td>
        </tr></tbody></table>
        """
        records = app.parse_records(html, "ETAX")
        self.assertEqual(app.page_count(html, "ETAX"), 3)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].ma_ho_so, "11320250292469209")
        self.assertEqual(records[0].loai_to_khai, "Chính thức")
        self.assertEqual(records[0].ky_tinh_thue, "12/2024")

    def test_ten_zip_co_thong_tin_to_khai(self):
        record = app.CaseRecord(
            ma_ho_so="11320250292469209",
            nguon="ETAX",
            to_khai="TỜ KHAI THUẾ GIÁ TRỊ GIA TĂNG",
            ky_tinh_thue="12/2024",
            loai_to_khai="Chính thức",
        )
        filename = app.zip_filename(record)
        self.assertIn("12-2024", filename)
        self.assertIn("Chinh-thuc", filename)
        self.assertIn("TO-KHAI-THUE-GIA-TRI-GIA-TANG", filename)


if __name__ == "__main__":
    unittest.main()
