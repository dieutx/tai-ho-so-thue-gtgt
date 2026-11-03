"""Tài khoản cá nhân: đăng nhập DVC, kho riêng và giới hạn luồng đã xác minh.

HAR `tk ca nhan dichvucong.gdt.gov.vn.har` xác nhận đăng nhập DVC với
``doiTuong=CN`` và tra cứu/tải tờ khai qua ``/tthc/ho-so/search`` +
``/tthc/tchs/downloadhoso``. Giấy nộp tiền và thông báo dùng
``canhan.gdt.gov.vn`` nên chưa được giả lập trong bộ test này.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from gdt_tax import auth
from gdt_tax.config import Settings
from gdt_tax.run_hooks import RunHooks
from tests.support import FakeResponse, StubCaptcha

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def personal_settings(**overrides) -> Settings:
    return Settings.from_env(environ={}, env_file=None, username='synthetic-personal',
                             password='fixture', login_attempts=1, account_type='CN',
                             **overrides)


class PersonalAuthTests(unittest.TestCase):
    def test_dvc_login_sends_personal_doi_tuong(self):
        settings = personal_settings()
        http = Mock(hooks=RunHooks())
        http.get.return_value = FakeResponse('<meta name="csrf-token" content="token">')
        http.post.return_value = FakeResponse(json_payload={'status': '200'})
        solver = Mock()
        solver.solve.return_value = 'abc12'
        with patch('gdt_tax.auth.fetch_captcha', return_value=b'image'):
            self.assertTrue(auth.login(http, solver, settings))
        self.assertEqual(http.post.call_args.kwargs['data']['doiTuong'], 'CN')

    def test_enterprise_default_still_sends_dn(self):
        settings = Settings.from_env(environ={}, env_file=None, username='synthetic-company',
                                     password='fixture', login_attempts=1)
        http = Mock(hooks=RunHooks())
        http.get.return_value = FakeResponse('<meta name="csrf-token" content="token">')
        http.post.return_value = FakeResponse(json_payload={'status': '200'})
        solver = Mock()
        solver.solve.return_value = 'abc12'
        with patch('gdt_tax.auth.fetch_captcha', return_value=b'image'):
            self.assertTrue(auth.login(http, solver, settings))
        self.assertEqual(http.post.call_args.kwargs['data']['doiTuong'], 'DN')


class PersonalStorageTests(unittest.TestCase):
    def test_personal_output_is_separate_from_enterprise(self):
        from desktop.state import job_output

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enterprise = job_output(root, 'synthetic', 'tax')
            personal = job_output(root, 'synthetic', 'tax', 'CN')
            self.assertNotEqual(enterprise, personal)
            self.assertIn('ca-nhan', personal.parts)
            self.assertNotIn('ca-nhan', enterprise.parts)

    def test_credentials_namespace_is_separate(self):
        from desktop.account_store import target_name

        self.assertEqual(target_name('synthetic'), target_name('synthetic', 'DN'))
        self.assertNotEqual(target_name('synthetic'), target_name('synthetic', 'CN'))
        self.assertNotIn('synthetic', target_name('synthetic', 'CN'))


class PersonalRunConfigTests(unittest.TestCase):
    def test_personal_uses_dvc_for_all_dates(self):
        from desktop.services import RunConfig
        from desktop.settings_store import Preferences

        config = RunConfig('tax', Path('/tmp/personal-account-test'), username='synthetic',
                           password='fixture', account_type='CN', preferences=Preferences())
        settings = config.settings()
        self.assertEqual(settings.account_type, 'CN')
        self.assertTrue(settings.dvc_enabled)
        self.assertFalse(settings.legacy_etax)
        self.assertEqual(settings.etax_cutoff.year, 1900)


class PersonalSessionTests(unittest.TestCase):
    def test_personal_tax_uses_dvc_and_skips_legacy_login(self):
        from desktop.services import JobResult, RunConfig
        from desktop.sessions import ETaxSessionManager

        with tempfile.TemporaryDirectory() as directory:
            manager = ETaxSessionManager()
            self.addCleanup(manager.close)
            manager.set_account_type('CN')
            manager.dvc_http = Mock()
            config = RunConfig('tax', Path(directory), username='synthetic',
                               password='fixture', account_type='CN')
            with patch('desktop.sessions.run_online',
                       return_value=JobResult('SUCCESS', 'Thành công', config.output)) as run:
                result = manager.execute(config, RunHooks(), StubCaptcha(), None)
            self.assertEqual(result.state, 'SUCCESS')
            self.assertIs(run.call_args.kwargs['http'], manager.dvc_http)
            self.assertTrue(run.call_args.kwargs['authenticate'])
            self.assertFalse(run.call_args.kwargs['propagate_auth'] is False)
            self.assertEqual(manager.account.state, 'CONNECTED')
            manager.dvc_authenticated = True
            with patch('desktop.sessions.run_online',
                       return_value=JobResult('SUCCESS', 'Thành công', config.output)) as run:
                manager.execute(config, RunHooks(), StubCaptcha(), None)
            self.assertFalse(run.call_args.kwargs['authenticate'])

    def test_changing_type_closes_dvc_session(self):
        from desktop.sessions import ETaxSessionManager

        manager = ETaxSessionManager()
        self.addCleanup(manager.close)
        manager.set_account_type('CN')
        client = Mock()
        manager.dvc_http = client
        manager.dvc_authenticated = True
        manager.set_account_type('DN')
        client.close.assert_called_once()
        self.assertIsNone(manager.dvc_http)
        self.assertFalse(manager.dvc_authenticated)
        self.assertEqual(manager.account_type, 'DN')

    def test_personal_notice_is_reported_unsupported_without_network(self):
        from desktop.services import RunConfig
        from desktop.sessions import ETaxSessionManager

        with tempfile.TemporaryDirectory() as directory:
            manager = ETaxSessionManager()
            self.addCleanup(manager.close)
            manager.set_account_type('CN')
            config = RunConfig('notice', Path(directory), username='synthetic',
                               password='fixture', account_type='CN')
            result = manager.execute(config, RunHooks(), StubCaptcha(), None)
        self.assertEqual(result.state, 'ERROR')
        self.assertEqual(result.error_code, 'UNSUPPORTED_ACCOUNT_FLOW')
        self.assertIn('canhan.gdt.gov.vn', result.message)


if __name__ == '__main__':
    unittest.main()
