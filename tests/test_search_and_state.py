"""S07: tìm không dấu, lọc riêng tab, đếm đã lọc và lưu ngữ cảnh UI."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None

from desktop.domain import period_key  # noqa: E402


class PeriodKeyTests(unittest.TestCase):
    def test_quarter_month_and_year_sort_semantically(self):
        values = ['Quý 1/2026', '12/2024', 'Quý 4/2025', '2026']
        self.assertEqual(sorted(values, key=period_key), ['12/2024', 'Quý 4/2025', '2026', 'Quý 1/2026'])


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class SearchFilterStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.settings_store import SettingsStore
        from desktop.ui import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = SettingsStore(self.root / 'settings.json')
        self.window = MainWindow(self.store)

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    @staticmethod
    def tax_row(case: str, **extra) -> dict:
        row = {'ma_ho_so': case, 'nguon': 'DVC', 'to_khai': 'Tờ khai thuế GTGT',
               'ky_tinh_thue': 'Quý 3/2026', 'ngay_nop': '20/10/2026',
               'trang_thai': 'Đã chấp nhận', '_file_status': 'downloaded',
               '_cqt_status': 'accepted', '_cqt_status_label': 'Đã chấp nhận'}
        row.update(extra)
        return row

    @staticmethod
    def notice_row(number: str, title: str) -> dict:
        return {'message_id': 'msg-' + number, 'ma_tbao': '01', 'so_thong_bao': number,
                'ten_thong_bao': title, 'ngay_gui': '20/10/2026',
                'co_quan_gui': 'Cục Thuế', 'trang_thai': 'Đã xem', '_file_status': 'downloaded'}

    def test_search_ignores_vietnamese_diacritics(self):
        self.window.model.reset('tax', [self.tax_row('A')])
        self.window.search.setText('to khai')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.search.setText('chap nhan')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.search.setText('khong chap nhan')
        self.assertEqual(self.window.proxy_model.rowCount(), 0)

    def test_cqt_filter_uses_status_code(self):
        rows = [
            self.tax_row('A', _cqt_status='accepted'),
            self.tax_row('B', trang_thai='Không chấp nhận', _cqt_status='rejected', _notice_state='rejected',
                         _cqt_status_label='Không chấp nhận'),
            self.tax_row('C', trang_thai='Đã tiếp nhận', _cqt_status='received', _cqt_status_label='Đã tiếp nhận'),
            self.tax_row('D', trang_thai='', _cqt_status='unknown', _cqt_status_label='Chưa xác định'),
        ]
        self.window.model.reset('tax', rows)
        self.window.proxy_model.set_cqt_filter('rejected')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.proxy_model.set_cqt_filter('accepted')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.proxy_model.set_cqt_filter('unknown')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.proxy_model.set_cqt_filter('all')
        self.assertEqual(self.window.proxy_model.rowCount(), 4)

    def test_notice_type_filter_lists_only_real_values(self):
        self.window.tabs.setCurrentIndex(2)
        rows = [self.notice_row('1/TB', 'Thông báo nộp thuế'),
                self.notice_row('2/TB', 'Thông báo tiền thuế nợ'),
                self.notice_row('3/TB', 'Thông báo nộp thuế')]
        self.window.model.reset('notice', rows)
        self.window.refresh_type_filter()
        values = [self.window.type_filter.itemData(i) for i in range(self.window.type_filter.count())]
        self.assertIn('Thông báo nộp thuế', values)
        self.assertIn('Thông báo tiền thuế nợ', values)
        index = self.window.type_filter.findData('Thông báo nộp thuế')
        self.window.type_filter.setCurrentIndex(index)
        self.assertEqual(self.window.proxy_model.rowCount(), 2)

    def test_filtered_count_uses_visible_over_total(self):
        self.window.model.reset('tax', [self.tax_row('A'), self.tax_row('B'), self.tax_row('C')])
        self.window.search.setText('B')
        self.window.update_filtered_count()
        self.assertEqual(self.window.filtered_label.text(), 'Hiển thị 1/3')

    def test_period_sort_uses_semantic_key(self):
        from PySide6.QtCore import Qt

        from desktop.table_model import COLUMNS
        rows = [self.tax_row('A', ky_tinh_thue='Quý 1/2026'),
                self.tax_row('B', ky_tinh_thue='12/2024'),
                self.tax_row('C', ky_tinh_thue='Quý 4/2025')]
        self.window.model.reset('tax', rows)
        column = next(i for i, (key, _) in enumerate(COLUMNS['tax']) if key == 'ky_tinh_thue')
        self.window.proxy_model.sort(column, Qt.SortOrder.AscendingOrder)
        self.assertEqual(self.window.proxy_model.index(0, column).data(), '12/2024')
        self.assertEqual(self.window.proxy_model.index(1, column).data(), 'Quý 4/2025')
        self.assertEqual(self.window.proxy_model.index(2, column).data(), 'Quý 1/2026')

    def test_ui_state_persists_and_restores_filter_and_sort(self):
        from desktop.ui import MainWindow
        self.window.model.reset('tax', [self.tax_row('A', _file_status='failed')])
        self.window.search.setText('to khai')
        self.window.file_filter.setCurrentIndex(self.window.file_filter.findData('failed'))
        self.window.cqt_filter.setCurrentIndex(self.window.cqt_filter.findData('rejected'))
        self.window.save_tab()
        self.window.persist_ui_state()
        import json
        saved = json.loads(self.store.path.read_text(encoding='utf-8'))
        state = saved['ui_state']['tax']
        self.assertEqual(state['filter_text'], 'to khai')
        self.assertEqual(state['status_filter'], 'failed')
        self.assertEqual(state['cqt_filter'], 'rejected')
        second = MainWindow(self.store)
        self.addCleanup(second.close)
        self.assertEqual(second.search.text(), 'to khai')
        self.assertEqual(second.file_filter.currentData(), 'failed')
        self.assertEqual(second.cqt_filter.currentData(), 'rejected')

    def test_ui_state_does_not_persist_rows_or_credentials(self):
        self.window.model.reset('tax', [self.tax_row('SECRET-CASE')])
        self.window.save_tab()
        self.window.persist_ui_state()
        import json
        saved = json.loads(self.store.path.read_text(encoding='utf-8'))
        self.assertNotIn('SECRET-CASE', json.dumps(saved, ensure_ascii=False))
        self.assertNotIn('rows', saved['ui_state']['tax'])
        self.assertNotIn('password', saved)


if __name__ == '__main__':
    unittest.main()
