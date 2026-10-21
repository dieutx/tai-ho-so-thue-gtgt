"""Shared ETAX authentication, expiry, account isolation and serialized requests."""
from __future__ import annotations

import logging
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import requests

from desktop.services import RunConfig, run_offline
from desktop.sessions import ETaxSessionManager, SessionHttpClient, is_auth_failure
from desktop.settings_store import Preferences
from gdt_tax.constants import GNT_OPERATION, TB_OPERATION
from gdt_tax.run_hooks import RunHooks
from tests.support import FakeResponse, StubCaptcha, cleanup_temporary_directory
from tests.test_etax_legacy import make_legacy_handler
from tests.test_gnt import make_gnt_handler
from tests.test_tb import make_tb_handler


class CombinedSession:
    def __init__(self, state):
        self.state, self.headers = state, {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.closed = False
        self.active = 0
        self.max_active = 0

    def request(self, method, url, **kwargs):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            parsed = urlparse(url)
            path = parsed.path + ('?' + parsed.query if parsed.query else '')
            data = kwargs.get('data') or kwargs.get('params') or {}
            operation = data.get('dse_operationName') or parse_qs(parsed.query).get('dse_operationName', [''])[0]
            event = data.get('dse_nextEventName') or parse_qs(parsed.query).get('dse_nextEventName', [''])[0]
            if event == 'start' and operation == 'corpUserLoginProc':
                self.state.setdefault('accounts', []).append(data.get('_userName'))
            if event == 'query' and self.state.get('expire', 0):
                self.state['expire'] -= 1
                return FakeResponse('<html><form id="loginForm"></form></html>', url=url)
            if self.state.get('slow'):
                time.sleep(0.002)
            factory = make_gnt_handler if operation == GNT_OPERATION else make_tb_handler if operation == TB_OPERATION else make_legacy_handler
            return factory(self.state)(method, path, kwargs)
        finally:
            self.active -= 1

    def close(self):
        self.closed = True


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = {}
        self.transports = []

        def factory(**kwargs):
            transport = CombinedSession(self.state)
            self.transports.append(transport)
            return SessionHttpClient(session=transport, **kwargs)

        self.manager = ETaxSessionManager(client_factory=factory)
        self.config = RunConfig('tax', self.root, username='synthetic-taxpayer-QL', password='test-secret',
            preferences=Preferences(record_delay=0., page_delay=0., jitter=0., login_attempts=1, search_attempts=1))

    def tearDown(self):
        self.manager.close()
        cleanup_temporary_directory(self.temp)

    def run_mode(self, mode):
        config = replace(self.config, mode=mode, output=self.root / mode)
        config.validate()
        return self.manager.execute(config, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'))

    def test_three_operations_login_once_and_reuse_session(self):
        for mode in ('tax', 'gnt', 'notice'):
            result = self.run_mode(mode)
            self.assertEqual(result.state, 'SUCCESS', result.message)
            self.assertGreater(result.downloaded, 0)
        self.assertEqual(self.state['login_posts'], 1)
        self.assertEqual(len(self.transports), 1)
        self.assertTrue(self.manager.session.authenticated)

    def test_expired_session_reauthenticates_once_and_stops_if_still_expired(self):
        self.run_mode('tax')
        self.state['expire'] = 1
        self.assertEqual(self.run_mode('gnt').state, 'SUCCESS')
        self.assertEqual(self.state['login_posts'], 2)
        self.state['expire'] = 5
        self.assertEqual(self.run_mode('notice').state, 'ERROR')
        self.assertEqual(self.state['login_posts'], 3)
        self.assertEqual(self.manager.account.state, 'EXPIRED')

    def test_change_account_clears_clients_cookies_and_dse(self):
        self.run_mode('tax')
        old = self.transports[0]
        old.cookies.set('session', 'old-private-cookie')
        self.manager.set_account('second-testpayer', 'another-secret')
        self.assertTrue(old.closed)
        self.assertFalse(list(old.cookies))
        self.assertFalse(self.manager.session.authenticated)
        self.config = replace(self.config, username='second-testpayer', password='another-secret')
        self.run_mode('notice')
        self.assertEqual(self.state['accounts'], ['synthetic-taxpayer-QL', 'second-testpayer'])
        self.manager.logout()
        self.assertEqual(self.manager.account.password, '')
        self.assertEqual(self.manager.account.username, '')

    def test_two_threads_serialize_access(self):
        self.state['slow'] = True
        results = []
        first = Thread(target=lambda: results.append(self.run_mode('gnt')))
        second = Thread(target=lambda: results.append(self.run_mode('notice')))
        first.start()
        second.start()
        first.join(10)
        second.join(10)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.state == 'SUCCESS' for r in results))
        self.assertEqual(self.state['login_posts'], 1)
        self.assertEqual(self.transports[0].max_active, 1)

    def test_page_open_failure_does_not_reauthenticate_without_expiry_evidence(self):
        from unittest.mock import patch

        from desktop.services import JobResult
        from gdt_tax.errors import LegacyPageError

        attempts = []

        def fake_run_online(config, hooks, captcha, logger, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise LegacyPageError(
                    "Không mở được trang tra cứu giấy nộp tiền legacy (HTTP 200)"
                )
            return JobResult("SUCCESS", "Thành công", config.output)

        with patch("desktop.sessions.run_online", side_effect=fake_run_online):
            result = self.run_mode("gnt")
        self.assertEqual(result.state, "ERROR")
        self.assertEqual(result.error_code, 'AUTH_SCHEMA_UNKNOWN')
        self.assertEqual(len(attempts), 1)
        self.assertEqual(self.state["login_posts"], 1)
        self.assertTrue(self.manager.session.authenticated)

    def test_page_open_failure_twice_reports_page_detail(self):
        from unittest.mock import patch

        from gdt_tax.errors import LegacyPageError

        detail = "Không mở được trang tra cứu thông báo legacy (HTTP 200): Hệ thống đang bảo trì"

        with patch("desktop.sessions.run_online", side_effect=LegacyPageError(detail)):
            result = self.run_mode("notice")
        self.assertEqual(result.state, "ERROR")
        self.assertEqual(result.error_code, 'AUTH_SCHEMA_UNKNOWN')
        self.assertNotIn(detail, result.message)
        self.assertEqual(self.state["login_posts"], 1)
        self.assertTrue(self.manager.session.authenticated)

    def test_offline_does_not_initialize_any_client(self):
        config = replace(self.config, mode='offline', source=Path('tests/fixtures'), stage='inventory')
        config.validate()
        run_offline(config, RunHooks(Event()), logging.getLogger('gdt_tax.test'))
        self.assertEqual(self.transports, [])

    def test_auth_detection_does_not_confuse_html_server_errors(self):
        for status in (401,):
            self.assertTrue(is_auth_failure(FakeResponse(status_code=status)))
        self.assertFalse(is_auth_failure(FakeResponse(status_code=403)))
        self.assertTrue(is_auth_failure(FakeResponse('<form id="loginForm">')))
        self.assertFalse(is_auth_failure(FakeResponse('<html>Gateway failure</html>', status_code=500)))

    def test_notice_http_200_without_form_is_error_without_six_retries_or_false_empty(self):
        self.config = replace(self.config, preferences=replace(self.config.preferences, search_attempts=6))
        with patch('gdt_tax.tb.portal.TbPortal._query_page_one',
                   return_value=FakeResponse('<html>Trang bảo trì</html>')) as query:
            result = self.run_mode('notice')
        self.assertEqual(result.state, 'ERROR')
        self.assertIn('thiếu bảng/form thông báo', result.message)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(self.state['login_posts'], 1)
