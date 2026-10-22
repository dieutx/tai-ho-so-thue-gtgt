"""User flows from the desktop usability review; no tax account or network."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tests.support import cleanup_temporary_directory

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class DesktopUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.settings_store import Preferences, SettingsStore
        from desktop.ui import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        store = SettingsStore(self.root / 'settings.json')
        store.save(Preferences(output=str(self.root)))
        self.window = MainWindow(store)

    def tearDown(self):
        self.window.close()
        cleanup_temporary_directory(self.temp)

    @staticmethod
    def row(case, status='downloaded'):
        return {'ma_ho_so': case, 'nguon': 'DVC', 'to_khai': 'Tờ khai GTGT',
                '_file_status': status, '_cqt_status': 'accepted'}

    def test_reset_filters_restores_rows_and_preserves_hidden_selection(self):
        from desktop.documents import document_id
        rows = [self.row('first'), self.row('second', 'failed')]
        self.window.model.reset('tax', rows)
        self.window.model.checked = {document_id('tax', rows[0])}
        self.window.search.setText('second')
        self.window.file_filter.setCurrentIndex(self.window.file_filter.findData('failed'))
        self.window.cqt_filter.setCurrentIndex(self.window.cqt_filter.findData('rejected'))
        self.assertEqual(self.window.proxy_model.rowCount(), 0)
        self.assertIn('1 đang ẩn', self.window.selection_label.text())
        self.assertTrue(self.window.reset_filters_button.isEnabled())
        self.window.reset_filters_button.click()
        self.assertEqual(self.window.proxy_model.rowCount(), 2)
        self.assertEqual(self.window.model.checked, {document_id('tax', rows[0])})
        self.assertNotIn('đang ẩn', self.window.selection_label.text())
        self.assertFalse(self.window.reset_filters_button.isEnabled())
        self.window.tabs.setCurrentIndex(1)
        self.window.search.setText('gnt-only')
        self.window.tabs.setCurrentIndex(0)
        self.window.reset_filters()
        self.window.tabs.setCurrentIndex(1)
        self.assertEqual(self.window.search.text(), 'gnt-only')

    def test_reset_filters_clears_notice_type(self):
        self.window.tabs.setCurrentIndex(2)
        self.window.model.reset('notice', [
            {'message_id': str(i), 'ten_thong_bao': title, '_file_status': 'downloaded'}
            for i, title in enumerate(['Nộp thuế', 'Tiền thuế nợ'])])
        self.window.type_filter.setCurrentIndex(1)
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.reset_filters_button.click()
        self.assertEqual(self.window.proxy_model.rowCount(), 2)

    def test_manual_source_edit_discards_previous_explicit_file_selection(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        old = self.root / 'old.xml'
        old.write_text('<fixture/>', encoding='utf-8')
        new = self.root / 'new'
        new.mkdir()
        self.window.tabs.setCurrentIndex(3)
        self.window.set_source_files([str(old)])
        self.window.show()
        self.app.processEvents()
        self.window.input_path.setFocus()
        QTest.keyClick(self.window.input_path, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(self.window.input_path, str(new))
        self.window.search.setFocus()
        self.assertFalse(self.window.source_files)
        self.assertEqual(self.window.source_info.text(), '')
        config = self.window.make_config('offline')
        self.assertEqual(config.source, new.resolve())
        self.assertEqual(config.source_files, ())

    def test_invalid_dates_are_explained_before_login_or_job(self):
        from PySide6.QtCore import QDate
        self.window.from_date.setDate(QDate(2026, 10, 22))
        self.window.to_date.setDate(QDate(2026, 9, 1))
        with patch.object(self.window, 'error') as error, patch.object(self.window, 'open_login') as login, patch.object(self.window.controller, 'start') as start:
            self.window.start(True)
        self.assertIn('Từ ngày', error.call_args.args[0])
        login.assert_not_called()
        start.assert_not_called()

    def test_missing_offline_source_is_explained_without_starting(self):
        self.window.tabs.setCurrentIndex(3)
        with patch.object(self.window, 'error') as error, patch.object(self.window.controller, 'start') as start:
            self.window.start(False)
        self.assertIn('nguồn', error.call_args.args[0])
        start.assert_not_called()

    def test_conflicting_output_owner_does_not_escape_ui_callback(self):
        from gdt_tax.identity import IdentityError
        self.window.controller.sessions.set_account('fixture-user', 'fixture-password')
        with patch('desktop.ui.job_output', side_effect=IdentityError('DIRECTORY_OWNER_MISMATCH: private-detail')), patch.object(self.window, 'error') as error, patch.object(self.window.controller, 'start') as start:
            self.window.start(False)
        self.assertIn('đúng tài khoản', error.call_args.args[0])
        self.assertNotIn('private-detail', error.call_args.args[0])
        start.assert_not_called()
        with patch.object(self.window, 'make_config', side_effect=IdentityError('private-detail')), patch.object(self.window, 'error') as error, patch.object(self.window.controller, 'start') as start:
            self.window.start_batch()
        self.assertIn('đúng tài khoản', error.call_args.args[0])
        self.assertNotIn('private-detail', error.call_args.args[0])
        start.assert_not_called()

    def test_incomplete_empty_result_does_not_claim_no_records(self):
        from desktop.services import JobResult
        for state in ['PARTIAL', 'CANCELLED']:
            with self.subTest(state=state):
                self.window.result = JobResult(state, 'incomplete', self.root)
                self.window.update_empty()
                self.assertIn('chưa thể kết luận', self.window.empty.text())

    def test_batch_directory_error_preserves_completed_groups_and_continues(self):
        from threading import Event

        from desktop.jobs import Redactor, Worker
        from desktop.services import JobResult, RunConfig
        from gdt_tax.identity import IdentityError
        config = RunConfig('batch', self.root, username='fixture-user', password='fixture-password')
        first = JobResult('SUCCESS', 'first done', self.root / 'tax',
                          rows=[self.row('completed')], files=[self.root / 'tax' / 'completed.zip'],
                          downloaded=1, discovered=1)
        third = JobResult('SUCCESS', 'third done', self.root / 'notice', downloaded=1)
        sessions = Mock()
        sessions.execute.side_effect = [first, third]
        worker = Worker(config, Event(), Redactor(config), sessions)
        completed = []
        worker.done.connect(completed.append)
        with patch.object(config, 'validate'), patch('desktop.jobs.GuiCaptchaSolver'), patch('desktop.jobs.job_output', side_effect=[self.root / 'tax', IdentityError('DIRECTORY_ACCOUNT_MISMATCH'), self.root / 'notice']):
            worker.run()
        result, = completed
        self.assertEqual(result.state, 'PARTIAL')
        self.assertEqual(set(result.children), {'tax', 'gnt', 'notice'})
        self.assertIs(result.children['tax'], first)
        self.assertEqual(result.children['gnt'].state, 'ERROR')
        self.assertEqual(result.children['notice'].state, 'SUCCESS')
        self.assertEqual(result.downloaded, 2)
        self.assertEqual(result.files, first.files)
        self.assertEqual(sessions.execute.call_count, 2)

    def test_populated_toolbar_fits_compact_window_with_all_actions(self):
        from desktop.services import JobResult
        rows = [self.row('first'), self.row('second', 'failed')]
        self.window.result = JobResult('PARTIAL', 'fixture', self.root, rows=rows)
        self.window.model.reset('tax', rows)
        self.window.populate_result(self.window.result)
        self.window.show()
        self.app.processEvents()
        for width, height in [(1024, 680), (680, 460)]:
            self.window.resize(width, height)
            self.app.processEvents()
            with self.subTest(size=(width, height)):
                self.assertLessEqual(self.window.width(), width)
                self.assertLessEqual(self.window.height(), height)
                for widget in [self.window.search, self.window.reset_filters_button,
                               self.window.file_filter, self.window.cqt_filter,
                               self.window.missing_button, self.window.retry_button,
                               self.window.verify_button, self.window.start_button]:
                    self.assertTrue(widget.isVisible())
                    origin = widget.mapTo(self.window, widget.rect().topLeft())
                    corner = widget.mapTo(self.window, widget.rect().bottomRight())
                    self.assertTrue(self.window.rect().contains(origin))
                    self.assertTrue(self.window.rect().contains(corner))


if __name__ == '__main__':
    unittest.main()
