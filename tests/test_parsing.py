import unittest

from gdt_tax.constants import SOURCE_DVC, SOURCE_ETAX, SOURCE_ETAX_LEGACY
from gdt_tax.parsing import (
    legacy_transaction_ids,
    page_count,
    parse_records,
)
from tests.support import fixture


class EtaxParsingTests(unittest.TestCase):
    def setUp(self):
        self.html = fixture("etax_results.html")

    def test_doc_dung_hai_ho_so(self):
        records = parse_records(self.html, SOURCE_ETAX)
        self.assertEqual(
            [record.ma_ho_so for record in records],
            ["11320250292469209", "11320250292528963"],
        )

    def test_lay_du_thong_tin_to_khai(self):
        record = parse_records(self.html, SOURCE_ETAX)[0]
        self.assertEqual(record.nguon, SOURCE_ETAX)
        self.assertEqual(record.ky_tinh_thue, "12/2024")
        self.assertEqual(record.loai_to_khai, "Chính thức")
        self.assertEqual(record.lan_nop, "1")
        self.assertEqual(record.lan_bo_sung, "0")
        self.assertEqual(record.ngay_nop, "20/01/2025 17:11:35")
        self.assertEqual(record.noi_nop, "Thuế cơ sở 1 tỉnh Hà Tĩnh")
        self.assertTrue(record.trang_thai.startswith("Cơ quan thuế chấp nhận"))
        self.assertTrue(record.to_khai.startswith("TỜ KHAI THUẾ GIÁ TRỊ GIA TĂNG"))

    def test_etax_khong_co_ten_tthc(self):
        record = parse_records(self.html, SOURCE_ETAX)[0]
        self.assertEqual(record.ten_tthc, "")

    def test_so_trang_etax(self):
        self.assertEqual(page_count(self.html, SOURCE_ETAX), 1)


class DvcParsingTests(unittest.TestCase):
    def setUp(self):
        self.html = fixture("dvc_results_page1.html")

    def test_doc_dung_hai_ho_so(self):
        records = parse_records(self.html, SOURCE_DVC)
        self.assertEqual(
            [record.ma_ho_so for record in records],
            ["G12.18-260120-21010800254723", "G12.18-260120-21010800167745"],
        )

    def test_lay_du_thong_tin_dvc(self):
        record = parse_records(self.html, SOURCE_DVC)[0]
        self.assertEqual(record.nguon, SOURCE_DVC)
        self.assertTrue(record.ten_tthc.startswith("1.007014"))
        self.assertTrue(record.to_khai.startswith("01/GTGT"))
        self.assertEqual(record.ky_tinh_thue, "12/2025")
        self.assertEqual(record.loai_to_khai, "Chính thức")
        self.assertEqual(record.lan_nop, "1")
        self.assertEqual(record.lan_bo_sung, "0")
        self.assertEqual(record.ngay_nop, "20/01/2026 13:51")
        self.assertEqual(record.trang_thai, "Đã chấp nhận")
        self.assertEqual(record.ho_so_dinh_kem, "1")

    def test_ho_so_bo_sung_duoc_nhan_dien(self):
        record = parse_records(self.html, SOURCE_DVC)[1]
        self.assertEqual(record.loai_to_khai, "Bổ sung")

    def test_so_trang_dvc(self):
        self.assertEqual(page_count(self.html, SOURCE_DVC), 2)


class RobustnessTests(unittest.TestCase):
    def test_bo_qua_hang_thieu_cot(self):
        html = "<table><tbody><tr><td>1</td><td>abc</td></tr></tbody></table>"
        self.assertEqual(parse_records(html, SOURCE_ETAX), [])
        self.assertEqual(parse_records(html, SOURCE_DVC), [])

    def test_bo_trung_theo_ma_ho_so(self):
        row = """
        <tr>
          <td>1</td><td>ABC-1</td><td>Tờ khai</td><td>12/2024</td><td>Chính thức</td>
          <td>1</td><td>0</td><td>20/01/2025</td><td>Nơi nộp</td><td>Đã nhận</td>
          <td><i data-ma-ho-so="ABC-1"></i></td>
        </tr>
        """
        html = f"<table><tbody>{row}{row}</tbody></table>"
        self.assertEqual(len(parse_records(html, SOURCE_ETAX)), 1)

    def test_so_trang_khi_cong_khong_bao(self):
        self.assertIsNone(page_count("<div></div>", SOURCE_DVC))
        self.assertIsNone(page_count("<div></div>", SOURCE_ETAX))


class LegacyTransactionTests(unittest.TestCase):
    def test_doc_cap_ma_ho_so_va_ctmagdich(self):
        records = parse_records(fixture("etax_legacy_results.html"), SOURCE_ETAX_LEGACY)
        mapping = legacy_transaction_ids(fixture("etax_legacy_results.html"))
        self.assertEqual(
            [record.ma_ho_so for record in records],
            ["11320200101110001", "11320200101110002"],
        )
        self.assertEqual(mapping["11320200101110001"], "11320200101119001")
        self.assertEqual(mapping["11320200101110002"], "11320200101119002")

    def test_hang_khong_co_lien_ket_thong_bao_bi_bo_qua(self):
        html = (
            "<table id='data_content_onday'><tr>"
            "<td><a onclick=\"downloadTkhai('ABC')\">Tải tờ khai</a></td>"
            "</tr></table>"
        )
        self.assertEqual(legacy_transaction_ids(html), {})

    def test_footer_row_without_handler_is_not_a_schema_error(self):
        from gdt_tax.parsing import parse_record_table
        header = (
            "<tr><th>STT</th><th>Mã giao dịch</th><th>Tờ khai/Phụ lục</th>"
            "<th>Kỳ tính thuế</th><th>Loại tờ khai</th><th>Lần nộp</th>"
            "<th>Lần bổ sung</th><th>Ngày nộp</th><th></th><th>Nơi nộp</th>"
            "<th>Trạng thái</th><th>Thao tác</th></tr>"
        )
        footer = "<tr>" + "".join(
            f"<td>{'Tổng cộng' if index == 0 else ''}</td>" for index in range(12)
        ) + "</tr>"
        html = fixture("etax_legacy_results.html").replace(
            '<table id="data_content_onday">', '<table id="data_content_onday">' + header
        ).replace("</table>", footer + "</table>")
        parsed = parse_record_table(html, SOURCE_ETAX_LEGACY)
        self.assertEqual(len(parsed.records), 2)
        self.assertEqual(parsed.diagnostics.skipped_count, 0)
        self.assertEqual(parsed.diagnostics.non_data_count, 1)
        self.assertEqual(parsed.diagnostics.status, "PARSED")
        self.assertFalse(any("RECORD_HANDLER_OR_ID_MISSING" in reason
                             for reason in parsed.diagnostics.reasons))

    def test_handler_with_mismatched_id_is_still_an_error(self):
        from gdt_tax.parsing import parse_record_table
        header = (
            "<tr><th>STT</th><th>Mã giao dịch</th><th>Tờ khai/Phụ lục</th>"
            "<th>Kỳ tính thuế</th><th>Loại tờ khai</th><th>Lần nộp</th>"
            "<th>Lần bổ sung</th><th>Ngày nộp</th><th></th><th>Nơi nộp</th>"
            "<th>Trạng thái</th><th>Thao tác</th></tr>"
        )
        cells = ['X', '999'] + [''] * 9 + [
            "<a onclick=\"downloadTkhai('ABC')\">Tải tờ khai</a>"
        ]
        bad = "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"
        html = fixture("etax_legacy_results.html").replace(
            '<table id="data_content_onday">', '<table id="data_content_onday">' + header
        ).replace("</table>", bad + "</table>")
        parsed = parse_record_table(html, SOURCE_ETAX_LEGACY)
        self.assertEqual(len(parsed.records), 2)
        self.assertEqual(parsed.diagnostics.skipped_count, 1)
        self.assertIn("RECORD_HANDLER_OR_ID_MISSING", parsed.diagnostics.reasons)


class UnknownSourceTests(unittest.TestCase):
    def test_nguon_la_thi_bao_loi_ngay(self):
        # Trước đây nguồn lạ bị đọc như DVC và cho ra hồ sơ sai cột.
        with self.assertRaises(ValueError):
            parse_records("<table><tbody></tbody></table>", "KHONG-CO")
        with self.assertRaises(ValueError):
            page_count("<html></html>", "KHONG-CO")


if __name__ == "__main__":
    unittest.main()
