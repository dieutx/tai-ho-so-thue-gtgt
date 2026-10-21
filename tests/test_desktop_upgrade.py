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
from tests.support import FakeResponse, cleanup_temporary_directory

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
    def test_five_rejected_ocr_attempts_before_manual_and_reset_on_success(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax.run_hooks import RunHooks
        requests = []
        def manual(request):
            requests.append(request)
            request.respond('AB123')
        solver = GuiCaptchaSolver(RunHooks(), manual, use_ocr=False)
        solver.ocr = Mock()
        solver.ocr.solve.return_value = 'OCR12'
        for _ in range(5):
            self.assertEqual(solver.solve(b'fixture'), 'OCR12')
            solver.rejected()
            self.assertEqual(requests, [])
        self.assertEqual(solver.solve(b'fixture'), 'AB123')
        self.assertEqual(solver.ocr.solve.call_count, 5)
        self.assertIn('5 lần', requests[0].message)
        solver.accepted()
        self.assertEqual(solver.solve(b'fixture'), 'OCR12')
        solver.close()

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_empty_or_crashing_ocr_retries_fresh_challenges_before_manual(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax.run_hooks import RunHooks
        for error in [None, RuntimeError('model unavailable')]:
            requests = []
            def manual(request, requests=requests):
                requests.append(request)
                request.respond('abc12')
            solver = GuiCaptchaSolver(RunHooks(), manual, use_ocr=False)
            solver.ocr = Mock()
            solver.ocr.solve.return_value = ''
            solver.ocr.solve.side_effect = error
            for number in range(4):
                self.assertEqual(solver.solve(f'image-{number}'.encode()), '')
                self.assertEqual(requests, [])
                solver.rejected()  # Empty OCR must not be counted twice.
            self.assertEqual(solver.solve(b'image-5'), 'abc12')
            self.assertEqual(solver.ocr.solve.call_count, 5)
            self.assertEqual(len(requests), 1)
            self.assertIn('5 lần', requests[0].message)

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_ocr_success_before_limit_never_requests_manual(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax.run_hooks import RunHooks
        request = Mock()
        solver = GuiCaptchaSolver(RunHooks(), request, use_ocr=False)
        solver.ocr = Mock()
        solver.ocr.solve.return_value = 'abc12'
        for _ in range(4):
            solver.solve(b'image')
            solver.rejected()
        self.assertEqual(solver.solve(b'image-5'), 'abc12')
        solver.accepted()
        request.assert_not_called()
        self.assertEqual(solver.auto_failures, 0)
        for _ in range(10):
            solver.solve(b'image')
            solver.accepted()
        request.assert_not_called()

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_cancel_during_ocr_does_not_turn_into_retry_or_manual(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax.run_hooks import RunCancelled, RunHooks
        request = Mock()
        solver = GuiCaptchaSolver(RunHooks(), request, use_ocr=False)
        solver.ocr = Mock()
        solver.ocr.solve.side_effect = RunCancelled('cancel')
        with self.assertRaises(RunCancelled):
            solver.solve(b'image')
        request.assert_not_called()

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_rejected_manual_fallback_stops_legacy_and_dvc_login(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax import auth
        from gdt_tax.errors import CaptchaError
        from gdt_tax.portals.etax_legacy import EtaxLegacyPortal
        from gdt_tax.run_hooks import RunHooks

        for portal_name in ['legacy', 'dvc']:
            with self.subTest(portal=portal_name):
                requests = []
                def manual(request, requests=requests):
                    requests.append(request)
                    request.respond('abc12')
                solver = GuiCaptchaSolver(RunHooks(), manual, use_ocr=False)
                solver.ocr = Mock()
                solver.ocr.solve.return_value = 'bad12'
                config = RunConfig('login', Path('fixture-output'), username='fixture', password='fixture')
                if portal_name == 'legacy':
                    portal = EtaxLegacyPortal(Mock(), solver, config.settings())
                    with patch.object(portal, '_legacy_captcha_image', return_value=b'fixture'), patch.object(portal, '_post_form', return_value=FakeResponse('<form id="loginForm"></form><div>invalid captcha</div>')) as post:
                        with self.assertRaisesRegex(CaptchaError, 'nhập tay'):
                            portal._submit_login(Mock(text='fixture', url='https://fixture.test'))
                else:
                    http = Mock()
                    http.get.return_value = FakeResponse(text='fixture')
                    http.post.return_value = FakeResponse(json_payload={'status': '401', 'code': 'CAPTCHA_INVALID'})
                    with patch('gdt_tax.auth.token_from_meta', return_value='fixture'), patch('gdt_tax.auth.fetch_captcha', return_value=b'fixture'):
                        with self.assertRaisesRegex(CaptchaError, 'nhập tay'):
                            auth.login(http, solver, config.settings())
                    post = http.post
                self.assertEqual(post.call_count, 6)
                self.assertEqual(solver.ocr.solve.call_count, 5)
                self.assertEqual(len(requests), 1)

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_ocr_diagnostics_distinguish_empty_output_and_exception_without_raw_error(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax.run_hooks import RunHooks
        solver = GuiCaptchaSolver(RunHooks(), Mock(), use_ocr=False)
        solver.ocr = Mock()
        solver.ocr.solve.return_value = ''
        with self.assertLogs(solver.logger, level='WARNING') as logs:
            self.assertEqual(solver.solve(b'fixture'), '')
        self.assertIn('rỗng', ' '.join(logs.output))
        solver.ocr.solve.side_effect = FileNotFoundError('private-account private-path')
        with self.assertLogs(solver.logger, level='WARNING') as logs:
            self.assertEqual(solver.solve(b'fixture'), '')
        message = ' '.join(logs.output)
        self.assertIn('FileNotFoundError', message)
        self.assertNotIn('private-account', message)
        self.assertNotIn('private-path', message)

    def test_gui_ocr_budget_leaves_room_for_manual_without_changing_cli(self):
        from gdt_tax.config import Settings
        for mode in ['tax', 'gnt', 'notice']:
            config = RunConfig(mode, Path('fixture-output'), username='fixture', password='fixture',
                               preferences=Preferences(login_attempts=1, search_attempts=1))
            self.assertEqual(config.settings().login_attempts, 6)
            self.assertEqual(config.settings().search_attempts, 6)
            config.preferences.solver = 'manual'
            self.assertEqual(config.settings().login_attempts, 1)
        settings = Settings.from_env(environ={}, env_file=None, username='fixture', password='fixture', login_attempts=1)
        self.assertEqual(settings.login_attempts, 1)

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_legacy_login_fetches_five_ocr_images_then_manual_on_sixth(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax.portals.etax_legacy import EtaxLegacyPortal
        from gdt_tax.run_hooks import RunHooks
        requests = []
        def manual(request):
            requests.append(request)
            request.respond('abc12')
        solver = GuiCaptchaSolver(RunHooks(), manual, use_ocr=False)
        solver.ocr = Mock()
        solver.ocr.solve.return_value = 'bad12'
        config = RunConfig('gnt', Path('fixture-output'), username='fixture', password='fixture', preferences=Preferences(login_attempts=1))
        portal = EtaxLegacyPortal(Mock(), solver, config.settings())
        failures = [FakeResponse('<form id="loginForm"></form><div>invalid captcha</div>', url='https://fixture.test')] * 5
        from gdt_tax.portals import etax_legacy
        success = FakeResponse(text=etax_legacy._LOGIN_OK_MARKER, url='https://fixture.test')
        with patch.object(portal, '_legacy_captcha_image', side_effect=[f'image-{n}'.encode() for n in range(6)]) as fetch, patch.object(portal, '_post_form', side_effect=failures + [success]) as post:
            self.assertIs(portal._submit_login(Mock(text='fixture', url='https://fixture.test')), success)
        self.assertEqual(fetch.call_count, 6)
        self.assertEqual(post.call_count, 6)
        self.assertEqual(solver.ocr.solve.call_count, 5)
        self.assertEqual(len(requests), 1)
        self.assertEqual(solver.auto_failures, 0)

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_dvc_search_acceptance_resets_ocr_failures_after_retries(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax.portals.dvc import DvcPortal
        from gdt_tax.run_hooks import RunHooks
        from tests.support import FakeResponse
        solver = GuiCaptchaSolver(RunHooks(), Mock(), use_ocr=False)
        solver.ocr = Mock()
        solver.ocr.solve.return_value = 'abc12'
        portal = DvcPortal(Mock(), solver, Mock())
        for _ in range(4):
            solver.solve(b'image')
            portal._page_result(FakeResponse(text='<html>CAPTCHA rejected</html>'))
        self.assertEqual(solver.auto_failures, 4)
        solver.solve(b'image-5')
        with patch('gdt_tax.portals.base.page_count', return_value=0):
            portal._page_result(FakeResponse(text='<html>empty but valid</html>'))
        self.assertEqual(solver.auto_failures, 4)
        portal._page_result(FakeResponse(text='<div id="table-container">Không có dữ liệu</div>'))
        self.assertEqual(solver.auto_failures, 0)
        solver.request.assert_not_called()

    @unittest.skipUnless(HAS_QT, 'Desktop Qt dependencies are optional for core-only installs')
    def test_dvc_login_retries_ocr_then_manual_with_new_image_each_time(self):
        from desktop.jobs import GuiCaptchaSolver
        from gdt_tax import auth
        from gdt_tax.run_hooks import RunHooks
        for success_at in [3, 5, 6]:
            requests = []
            def manual(request, requests=requests):
                requests.append(request)
                request.respond('abc12')
            solver = GuiCaptchaSolver(RunHooks(), manual, use_ocr=False)
            solver.ocr = Mock()
            solver.ocr.solve.return_value = 'abc12'
            config = RunConfig('tax', Path('fixture-output'), username='fixture', password='fixture', preferences=Preferences(login_attempts=1))
            http = Mock()
            http.get.return_value = FakeResponse(text='fixture')
            http.post.side_effect = [FakeResponse(json_payload={'status': '401', 'code': 'CAPTCHA_INVALID'}) for _ in range(success_at - 1)] + [FakeResponse(json_payload={'status': '200'})]
            images = [f'captcha-{number}'.encode() for number in range(success_at)]
            with patch('gdt_tax.auth.token_from_meta', return_value='fixture-csrf'), patch('gdt_tax.auth.fetch_captcha', side_effect=images) as fetch:
                self.assertTrue(auth.login(http, solver, config.settings()))
            self.assertEqual(fetch.call_count, success_at)
            self.assertEqual(solver.ocr.solve.call_count, min(success_at, 5))
            self.assertEqual(len(requests), 1 if success_at == 6 else 0)


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

    def test_login_error_shows_actual_verification_reason(self):
        from desktop.services import JobResult
        from desktop.ui import MainWindow
        from gdt_tax.verification import VERIFICATION_MESSAGE
        window = MainWindow(SettingsStore(self.root / 'settings.json'))
        window.active_config = RunConfig('login', self.root, username='fixture', password='fixture')
        with patch.object(window, 'error') as show_error:
            window.on_completed(JobResult('ERROR', VERIFICATION_MESSAGE, self.root))
        show_error.assert_called_once_with(VERIFICATION_MESSAGE)
        self.assertIn('xác minh trình duyệt', window.status.text())
        window.close()

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
