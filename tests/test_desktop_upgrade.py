"""Regression cases from live use: Windows locks, account dialog and DVC defaults."""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from desktop.services import RunConfig
from desktop.settings_store import Preferences, SettingsStore
from gdt_tax.atomic import replace_with_retry
from tests.support import cleanup_temporary_directory

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None


class AtomicRetryTests(unittest.TestCase):
    def test_windows_lock_is_retried_and_committed(self):
        error = PermissionError('locked')
        error.winerror = 5
        with patch('gdt_tax.atomic.os.replace', side_effect=[error, error, None]) as commit, patch('gdt_tax.atomic.time.sleep') as sleep:
            replace_with_retry('new.tmp', 'catalog.json')
        self.assertEqual(commit.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_permanent_access_denied_is_bounded(self):
        error = PermissionError('locked')
        error.winerror = 32
        with patch('gdt_tax.atomic.os.replace', side_effect=error) as commit, patch('gdt_tax.atomic.time.sleep'):
            with self.assertRaises(PermissionError):
                replace_with_retry('new.tmp', 'catalog.json')
        self.assertEqual(commit.call_count, 5)

    def test_default_dvc_is_on_without_changing_legacy_cli_default(self):
        self.assertTrue(Preferences().dvc_enabled)
        from gdt_tax.config import Settings
        settings = Settings.from_env(environ={}, env_file=None, username='test', password='test')
        self.assertFalse(settings.dvc_enabled)

    def test_default_folder_access_denied_is_bounded_without_tempfile_loop(self):
        from desktop.settings_store import default_output
        with patch.object(Path, 'mkdir'), patch.object(Path, 'open', side_effect=PermissionError('denied')) as probe:
            with self.assertRaisesRegex(OSError, 'Không tìm được thư mục'):
                default_output()
        self.assertEqual(probe.call_count, 4)

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_update_lookup_private_or_new_version_has_honest_message(self):
        from desktop.updates import release_message
        self.assertIn('riêng tư', release_message(Mock(return_value=Mock(status_code=404))))
        response = Mock(status_code=200)
        response.json.return_value = [{'tag_name': 'desktop-v999.0.0'}]
        self.assertIn('Có bản mới', release_message(Mock(return_value=response)))

    def test_metadata_access_denied_keeps_downloaded_rows_and_files(self):
        from desktop.services import ONLINE, run_online
        from gdt_tax.run_hooks import RunHooks
        from tests.support import FakeHttp, StubCaptcha
        from tests.test_gnt import make_gnt_handler
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            config = RunConfig('gnt', output, username='fixture-account', password='fixture-secret',
                               preferences=Preferences(record_delay=0, page_delay=0, jitter=0))
            config.validate()
            kind, _, report = ONLINE['gnt']
            with patch.dict(ONLINE, {'gnt': (kind, Mock(side_effect=PermissionError('locked')), report)}):
                result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'),
                                    http=FakeHttp(make_gnt_handler({})))
            self.assertEqual(result.state, 'ERROR')
            self.assertGreater(result.downloaded, 0)
            self.assertEqual(result.discovered, len(result.rows))
            self.assertTrue(list(output.glob('*.xml')))
            self.assertEqual(result.files, [])  # do not offer a possibly stale report after failed flush
            self.assertIn('Không lưu được danh mục', result.message)

    def test_mixed_dvc_failure_preserves_legacy_result(self):
        from desktop.services import JobResult
        from desktop.sessions import ETaxSessionManager
        from gdt_tax.run_hooks import RunHooks
        config = RunConfig('tax', Path('fixture-output'), username='fixture', password='fixture',
                           from_date='01/06/2025', to_date='31/07/2025', dvc=True)
        legacy = JobResult('SUCCESS', 'OK', config.output, rows=[{'ma_ho_so': 'fixture'}],
                           discovered=1, downloaded=1)
        manager = ETaxSessionManager()
        with patch.object(manager, 'execute', side_effect=[legacy, RuntimeError('DVC unavailable')]):
            result = manager._mixed_tax(config, RunHooks(), None, logging.getLogger('gdt_tax.test'))
        self.assertEqual(result.state, 'PARTIAL')
        self.assertEqual(result.rows, legacy.rows)
        self.assertEqual(result.downloaded, 1)
        self.assertEqual(result.errors, 1)

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_rejected_ocr_requires_manual_next_attempt(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax.run_hooks import RunHooks
        solver = GuiCaptchaSolver(RunHooks(), lambda request: request.respond('AB12'), use_ocr=False)
        solver.ocr = Mock()
        solver.ocr.solve.return_value = 'OCR1'
        self.assertEqual(solver.solve(b'fixture'), 'OCR1')
        solver.rejected()
        self.assertEqual(solver.solve(b'fixture'), 'AB12')
        self.assertEqual(solver.ocr.solve.call_count, 1)
        solver.accepted()
        self.assertEqual(solver.solve(b'fixture'), 'OCR1')
        solver.close()


@unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
class DesktopUpgradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def test_single_account_dialog_hold_to_reveal_and_clear_on_close(self):
        from PySide6.QtWidgets import QLineEdit, QPushButton

        from desktop.account_dialog import AccountDialog
        from desktop.ui import MainWindow
        window = MainWindow(SettingsStore(self.root / 'settings.json'))
        self.assertFalse(any(w.accessibleName() == 'Mật khẩu GDT' for w in window.findChildren(QLineEdit)))
        dialog = AccountDialog(window, 'fixture-account', 'fixture-secret')
        eye = next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Giữ để hiện')
        eye.pressed.emit()
        self.assertEqual(dialog.password.echoMode(), QLineEdit.EchoMode.Normal)
        eye.released.emit()
        self.assertEqual(dialog.password.echoMode(), QLineEdit.EchoMode.Password)
        dialog.reject()
        self.assertEqual(dialog.password.text(), '')
        self.assertIsNone(dialog.take_credentials())
        window.close()

    def test_ten_tab_cycles_do_not_login_and_each_tab_keeps_rows_and_filter(self):
        from desktop.services import JobResult
        from desktop.ui import MainWindow
        window = MainWindow(SettingsStore(self.root / 'settings.json'))
        window.show()
        self.app.processEvents()
        window.result = JobResult('SUCCESS', 'Fixture', self.root, rows=[{'to_khai': 'Tờ khai fixture', 'ma_ho_so': 'case-1'}], discovered=1)
        window.model.reset('tax', window.result.rows)
        window.search.setText('fixture')
        with patch.object(window.controller.sessions, 'ensure_authenticated', side_effect=AssertionError('tab performed login')):
            for _ in range(10):
                for index in range(4):
                    window.tabs.setCurrentIndex(index)
            window.tabs.setCurrentIndex(0)
        self.assertEqual(window.model.rowCount(), 1)
        self.assertEqual(window.search.text(), 'fixture')
        self.assertTrue(window.dvc)
        window.close()

    def test_saved_data_opens_without_account_or_network_and_copy_preserves_source(self):
        from desktop.migration import load_saved
        from gdt_tax.run_hooks import RunHooks
        source = self.root / 'old'
        source.mkdir()
        fixture = Path('tests/fixtures/gnt_chungtu.xml').read_bytes()
        (source / 'record.xml').write_bytes(fixture)
        rows = [{'ctu_id': 'fixture-1', 'so_gnt': 'fixture', 'tep_xml': 'record.xml'}]
        (source / 'danh_sach_giay_nop_tien.json').write_text(json.dumps(rows))
        config = RunConfig('saved', source, source=source, stage='gnt')
        config.validate()
        with patch('socket.socket.connect', side_effect=AssertionError('saved data accessed network')):
            result = load_saved(config, RunHooks())
            self.assertEqual(result.state, 'LOADED')
            self.assertEqual(result.downloaded, 1)
            target = self.root / 'new'
            target.mkdir()
            copied = load_saved(replace(config, output=target, mode='import'), RunHooks(), copy_files=True)
        self.assertEqual(copied.state, 'SUCCESS')
        self.assertEqual((target / 'record.xml').read_bytes(), fixture)
        self.assertEqual((source / 'record.xml').read_bytes(), fixture)
