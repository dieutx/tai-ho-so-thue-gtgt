"""S06: tab Thông báo thuế độc lập, dùng XML Viewer dùng chung."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None

from desktop.domain import BUSINESS_UNKNOWN, TaxNotice  # noqa: E402
from desktop.feedback_service import feedback_summary, list_tax_notices  # noqa: E402


def notice_row(path: str = '', **extra) -> dict:
    row = {'message_id': 'msg-1', 'ma_tbao': '01', 'so_thong_bao': '999/TB',
           'ten_thong_bao': 'Thông báo nộp thuế', 'ngay_gui': '20/10/2026',
           'co_quan_gui': 'Cục Thuế', 'trang_thai': 'Đã xem',
           '_file_status': 'downloaded', '_file_path': path, '_file_hash': 'hash', '_file_size': 10}
    row.update(extra)
    return row


class NoticeDataTests(unittest.TestCase):
    def test_declaration_feedback_and_independent_notice_stay_separate(self):
        tax_row = {'ma_ho_so': 'case-A', 'nguon': 'DVC', 'ky_tinh_thue': 'Quý 3/2026',
                   'ngay_nop': '20/10/2026', '_file_status': 'downloaded',
                   '_notices': [{'state': 'accepted', 'so_thong_bao': '999/TB',
                                 'name': 'a.xml', 'read_status': 'PARSED', 'kind': 'chap-nhan'}]}
        notice = notice_row('C:/ho-so/999.pdf')
        self.assertEqual(feedback_summary(tax_row).count, 1)
        self.assertEqual(feedback_summary(notice).count, 0)
        notices = list_tax_notices([tax_row, notice], taxpayer_key='mst-A')
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].number, '999/TB')
        self.assertEqual(notices[0].business_result, BUSINESS_UNKNOWN)

    def test_tax_notice_key_is_namespaced_away_from_submission_key(self):
        notice = list_tax_notices(notice_row(), taxpayer_key='mst-A')[0]
        self.assertIn('message_id=msg-1', notice.tax_notice_key)
        self.assertNotIn('source=DVC', notice.tax_notice_key)


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class NoticeUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.settings_store import SettingsStore
        from desktop.ui import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = MainWindow(SettingsStore(self.root / 'settings.json'))

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    def test_notice_table_has_separate_business_columns(self):
        from desktop.table_model import COLUMNS
        headers = dict(COLUMNS['notice'])
        self.assertEqual(headers['ten_thong_bao'], 'Loại / Tên thông báo')
        self.assertEqual(headers['so_thong_bao'], 'Số thông báo')
        self.assertEqual(headers['co_quan_gui'], 'Cơ quan phát hành')
        self.assertEqual(headers['_file_status'], 'Trạng thái tải')
        self.assertNotIn('Số / Tên thông báo', headers.values())
        self.assertNotIn('Tệp PDF', headers.values())

    def test_notice_row_displays_number_issuer_and_download_state(self):
        from PySide6.QtCore import Qt

        from desktop.table_model import COLUMNS
        self.window.model.reset('notice', [notice_row()])
        column = {key: index for index, (key, _) in enumerate(COLUMNS['notice'])}
        self.assertEqual(self.window.model.index(0, column['ten_thong_bao']).data(), 'Thông báo nộp thuế')
        self.assertEqual(self.window.model.index(0, column['so_thong_bao']).data(), '999/TB')
        self.assertEqual(self.window.model.index(0, column['co_quan_gui']).data(), 'Cục Thuế')
        self.assertEqual(self.window.model.index(0, column['_file_status']).data(), 'Đã tải')
        self.assertEqual(self.window.model.index(0, column['_action']).data(), 'Xem tệp')
        self.assertIn('999/TB', self.window.model.index(
            0, column['so_thong_bao']).data(Qt.ItemDataRole.ToolTipRole))

    def test_open_notice_uses_tax_notice_owner_not_feedback_selector(self):
        pdf = self.root / '999.pdf'
        pdf.write_bytes(b'%PDF-1.4\nfixture')
        row = notice_row(str(pdf))
        with patch('desktop.xml_viewer.XmlViewer.show_asset') as opener:
            self.window.open_notice_row(row)
        opener.assert_called_once()
        asset = opener.call_args.args[1]
        summary = opener.call_args.kwargs['summary']
        self.assertEqual(opener.call_args.kwargs['source_kind'], 'tax_notice')
        self.assertEqual(asset.owner_kind, 'tax_notice')
        self.assertEqual(asset.original_filename, '999.pdf')
        self.assertIsInstance(summary, TaxNotice)
        self.assertEqual(summary.number, '999/TB')
        self.assertEqual(summary.business_result, BUSINESS_UNKNOWN)

    def test_missing_notice_file_is_reported_without_fake_viewer(self):
        row = notice_row('C:/khong-ton-tai/999.pdf')
        with patch.object(self.window, 'error') as error:
            with patch('desktop.xml_viewer.XmlViewer.show_asset') as opener:
                self.window.open_notice_row(row)
        error.assert_called_once()
        opener.assert_not_called()

    def test_switch_to_notice_tab_clears_feedback_panel(self):
        tax_row = {'ma_ho_so': 'case-A', 'nguon': 'DVC', 'to_khai': 'Tờ khai A',
                   '_file_status': 'not_downloaded', '_notices': [
                       {'state': 'accepted', 'so_thong_bao': 'A/TB', 'name': 'a.xml',
                        'read_status': 'PARSED', 'kind': 'chap-nhan'}]}
        self.window.model.reset('tax', [tax_row])
        self.window.show_feedback_panel(tax_row)
        self.assertEqual(self.window.feedback_panel.table.rowCount(), 1)
        self.window.tabs.setCurrentIndex(2)
        self.assertEqual(self.window.current_mode, 'notice')
        self.assertEqual(self.window.feedback_panel.items, [])
        self.assertTrue(self.window.feedback_panel.isHidden())

    def test_notice_search_is_independent_from_feedback_text(self):
        self.window.model.reset('notice', [notice_row()])
        self.window.proxy_model.setFilterFixedString('999/TB')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.proxy_model.setFilterFixedString('Cục Thuế')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.proxy_model.setFilterFixedString('khong-chap-nhan.xml')
        self.assertEqual(self.window.proxy_model.rowCount(), 0)
        self.window.proxy_model.setFilterFixedString('')

    def test_notice_tab_hides_review_filter_without_feedback_state(self):
        self.window.tabs.setCurrentIndex(2)
        self.assertTrue(self.window.file_filter.view().isRowHidden(4))


if __name__ == '__main__':
    unittest.main()
