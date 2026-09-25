import unittest
from datetime import date, datetime

from gdt_tax.constants import SOURCE_DVC, SOURCE_ETAX
from gdt_tax.dates import (
    ETAX_CUTOFF_DEFAULT,
    MAX_DAYS_PER_SEARCH_DEFAULT,
    format_date,
    parse_date,
    source_for,
    split_periods,
)


class ParseDateTests(unittest.TestCase):
    def test_doc_chuoi_dd_mm_yyyy(self):
        self.assertEqual(parse_date("01/02/2025"), date(2025, 2, 1))

    def test_giu_nguyen_date_va_datetime(self):
        self.assertEqual(parse_date(date(2025, 2, 1)), date(2025, 2, 1))
        self.assertEqual(parse_date(datetime(2025, 2, 1, 9, 30)), date(2025, 2, 1))

    def test_sai_dinh_dang_thi_bao_loi(self):
        with self.assertRaises(ValueError):
            parse_date("2025-02-01")

    def test_format_date_dung_dinh_dang_cong(self):
        self.assertEqual(format_date(date(2025, 2, 1)), "01/02/2025")


class SourceForTests(unittest.TestCase):
    def test_truoc_moc_dung_etax(self):
        self.assertEqual(source_for(date(2025, 6, 30)), SOURCE_ETAX)

    def test_tu_moc_tro_di_dung_dvc(self):
        self.assertEqual(source_for(ETAX_CUTOFF_DEFAULT), SOURCE_DVC)
        self.assertEqual(source_for(date(2025, 7, 2)), SOURCE_DVC)


class SplitPeriodsTests(unittest.TestCase):
    def test_chia_khoang_vat_qua_moc(self):
        periods = list(split_periods("15/05/2025", "05/07/2025"))
        self.assertEqual(
            [(p.start, p.end, p.source) for p in periods],
            [
                (date(2025, 5, 15), date(2025, 6, 14), SOURCE_ETAX),
                (date(2025, 6, 15), date(2025, 6, 30), SOURCE_ETAX),
                (date(2025, 7, 1), date(2025, 7, 5), SOURCE_DVC),
            ],
        )

    def test_mot_thang_du_31_ngay_la_mot_doan(self):
        periods = list(split_periods("01/01/2025", "31/01/2025"))
        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].source, SOURCE_ETAX)

    def test_32_ngay_bi_cat_thanh_hai_doan(self):
        periods = list(split_periods("01/01/2026", "01/02/2026"))
        self.assertEqual(
            [(p.start, p.end, p.source) for p in periods],
            [
                (date(2026, 1, 1), date(2026, 1, 31), SOURCE_DVC),
                (date(2026, 2, 1), date(2026, 2, 1), SOURCE_DVC),
            ],
        )

    def test_moi_doan_toi_da_31_ngay_trong_ca_nam(self):
        periods = list(split_periods("01/01/2026", "31/12/2026"))
        self.assertTrue(periods)
        for period in periods:
            self.assertLessEqual((period.end - period.start).days + 1, MAX_DAYS_PER_SEARCH_DEFAULT)

    def test_doan_etax_khong_bao_gio_vuot_moc(self):
        periods = list(split_periods("01/06/2025", "31/08/2025"))
        etax = [p for p in periods if p.source == SOURCE_ETAX]
        self.assertTrue(etax)
        for period in etax:
            self.assertLess(period.end, ETAX_CUTOFF_DEFAULT)

    def test_moc_va_so_ngay_tuy_chinh(self):
        periods = list(
            split_periods("01/01/2020", "31/01/2020", cutoff=date(2020, 1, 15), max_days=10)
        )
        self.assertEqual(
            [(p.source, p.end) for p in periods],
            [
                (SOURCE_ETAX, date(2020, 1, 10)),
                (SOURCE_ETAX, date(2020, 1, 14)),
                (SOURCE_DVC, date(2020, 1, 24)),
                (SOURCE_DVC, date(2020, 1, 31)),
            ],
        )

    def test_ngay_bat_dau_sau_ngay_ket_thuc_thi_bao_loi(self):
        with self.assertRaises(ValueError):
            list(split_periods("01/02/2026", "01/01/2026"))

    def test_max_days_khong_hop_le_thi_bao_loi(self):
        with self.assertRaises(ValueError):
            list(split_periods("01/01/2026", "31/01/2026", max_days=0))

    def test_ngay_sai_dinh_dang_thi_bao_loi(self):
        with self.assertRaises(ValueError):
            list(split_periods("2026-01-01", "31/01/2026"))

    def test_label_doc_duoc(self):
        period = next(split_periods("01/01/2026", "31/01/2026"))
        self.assertEqual(period.label, "01/01/2026 - 31/01/2026")


if __name__ == "__main__":
    unittest.main()
