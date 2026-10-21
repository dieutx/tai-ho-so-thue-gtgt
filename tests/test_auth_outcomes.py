"""Synthetic evidence, not captures or claims about current portal behavior."""
from __future__ import annotations

import json
import logging
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop.services import RunConfig
from desktop.sessions import ETaxSessionManager
from gdt_tax import auth, cli
from gdt_tax.auth_outcomes import AuthFailure, AuthOutcome, classify_response
from gdt_tax.config import Settings
from gdt_tax.portals.etax_legacy import EtaxLegacyPortal
from gdt_tax.run_hooks import RunCancelled, RunHooks
from tests.support import FakeResponse, temporary_directory
from tests.test_etax_legacy import LOGIN_OK_HTML, LOGIN_PAGE_HTML
from tests.test_verification import CHALLENGE


class AuthContractTests(unittest.TestCase):
    def test_nested_hidden_nodes_do_not_destroy_pending_selector_matches(self):
        hidden = ('<div style="display:none"><span style="color:red">invalid credentials</span></div>'
                  '<div hidden><span hidden>invalid captcha</span></div>'
                  '<template><template>session expired</template></template>'
                  '<div style="visibility:hidden"><b style="display:none">under maintenance</b></div>')
        for adapter in ('DVC', 'ETAX_LEGACY'):
            with self.subTest(adapter=adapter):
                self.assertEqual(classify_response(FakeResponse(hidden), adapter), AuthOutcome.SCHEMA_UNKNOWN)
                self.assertEqual(classify_response(FakeResponse(hidden + '<p>invalid captcha</p>'), adapter), AuthOutcome.CAPTCHA_INVALID)
        self.assertEqual(classify_response(FakeResponse(hidden + LOGIN_OK_HTML), 'ETAX_LEGACY'), AuthOutcome.SUCCESS)

    def test_legacy_explicit_captcha_variant_is_retried_but_static_script_is_not(self):
        message = 'Mã xác thực không chính xác'
        self.assertEqual(classify_response(FakeResponse(LOGIN_PAGE_HTML + '<span>'+message+'</span>'), 'ETAX_LEGACY'), AuthOutcome.CAPTCHA_INVALID)
        self.assertEqual(classify_response(FakeResponse(LOGIN_PAGE_HTML + '<script>function unused(){alert("'+message+'");}</script>'), 'ETAX_LEGACY'), AuthOutcome.SCHEMA_UNKNOWN)

    def test_business_xml_text_is_not_an_authentication_error(self):
        body = '<?xml version="1.0"?><TBaoThueDTu>Mã xác thực không chính xác</TBaoThueDTu>'.encode()
        self.assertEqual(classify_response(FakeResponse(content=body), 'ETAX_LEGACY', phase='operation', authenticated=True), AuthOutcome.SCHEMA_UNKNOWN)
        self.assertEqual(classify_response(FakeResponse(content=body, status_code=401), 'ETAX_LEGACY', phase='operation', authenticated=True), AuthOutcome.EXPIRED_SESSION)

    def test_legacy_success_requires_reviewed_navigation_form_and_operation(self):
        for text in ('corporateHomeProc', '<script>var unused="corporateHomeProc";</script>',
                     LOGIN_OK_HTML.replace('corporateHomeProc', 'unreviewedOperation')):
            self.assertEqual(classify_response(FakeResponse(text), 'ETAX_LEGACY'), AuthOutcome.SCHEMA_UNKNOWN)
        self.assertEqual(classify_response(FakeResponse(LOGIN_OK_HTML), 'ETAX_LEGACY'), AuthOutcome.SUCCESS)
        self.assertEqual(classify_response(FakeResponse(LOGIN_OK_HTML.replace("id='goProcForm'", "id='goProcForm' hidden")), 'ETAX_LEGACY'), AuthOutcome.SUCCESS)

    def test_eight_outcomes_on_both_adapters(self):
        messages = {
            'INVALID_CREDENTIALS': 'Tên đăng nhập hoặc mật khẩu không chính xác',
            'CAPTCHA_INVALID': 'CAPTCHA không đúng',
            'EXPIRED_SESSION': 'Phiên làm việc đã hết hạn',
            'MAINTENANCE': 'Hệ thống đang bảo trì',
            'INTERACTIVE_AUTH_REQUIRED': '<form id="otpForm"><input autocomplete="one-time-code"></form>',
            'ACCESS_VERIFICATION': CHALLENGE,
            'SCHEMA_UNKNOWN': '<div>Unreviewed response</div>',
        }
        for adapter in ('DVC', 'ETAX_LEGACY'):
            for expected, text in messages.items():
                with self.subTest(adapter=adapter, expected=expected):
                    self.assertEqual(classify_response(FakeResponse(text), adapter), AuthOutcome(expected))
            success = (FakeResponse(json_payload={'status': '200'}) if adapter == 'DVC'
                       else FakeResponse(LOGIN_OK_HTML))
            self.assertEqual(classify_response(success, adapter), AuthOutcome.SUCCESS)
            for response in (FakeResponse(status_code=302, url='https://fixture.test/page', headers={'Location': '/login'}),
                             FakeResponse(url='https://fixture.test/Request?dse_nextEventName=login'),
                             FakeResponse(LOGIN_PAGE_HTML), FakeResponse(status_code=401)):
                self.assertEqual(classify_response(response, adapter, authenticated=True), AuthOutcome.EXPIRED_SESSION)
            self.assertEqual(classify_response(FakeResponse(status_code=403), adapter, authenticated=True), AuthOutcome.SCHEMA_UNKNOWN)
            self.assertEqual(classify_response(FakeResponse(status_code=503), adapter), AuthOutcome.MAINTENANCE)

    def test_static_hidden_validators_do_not_reject_ocr_or_credentials(self):
        text = ('<script>var x="invalid credentials";</script><style>invalid captcha</style>'
                '<div style="display: none">invalid credentials</div><span hidden>invalid captcha</span>'
                '<div aria-hidden="true">session expired</div>')
        for adapter in ('DVC', 'ETAX_LEGACY'):
            self.assertEqual(classify_response(FakeResponse(text), adapter), AuthOutcome.SCHEMA_UNKNOWN)
        self.assertEqual(classify_response(FakeResponse(json_payload={'status': 401}), 'DVC'), AuthOutcome.SCHEMA_UNKNOWN)

    def test_dvc_terminal_outcomes_do_not_retry_or_reject_solver(self):
        settings = Settings.from_env(environ={}, env_file=None, username='synthetic', password='fixture', login_attempts=6)
        for outcome in (AuthOutcome.INVALID_CREDENTIALS, AuthOutcome.MAINTENANCE, AuthOutcome.SCHEMA_UNKNOWN):
            http, solver = Mock(hooks=RunHooks()), Mock()
            solver.solve.return_value = 'abc12'
            http.get.return_value = FakeResponse('<meta name="csrf-token" content="token">')
            http.post.return_value = FakeResponse(json_payload={'code': outcome.value})
            with patch('gdt_tax.auth.fetch_captcha', return_value=b'synthetic'):
                with self.assertRaises(AuthFailure) as caught:
                    auth.login(http, solver, settings)
            self.assertEqual(caught.exception.code, 'AUTH_' + outcome.value)
            http.post.assert_called_once()
            solver.rejected.assert_not_called()

    def test_dvc_captcha_retry_uses_rotated_tokens_and_stops_at_budget(self):
        settings = Settings.from_env(environ={}, env_file=None, username='synthetic', password='fixture', login_attempts=2)
        http, solver = Mock(hooks=RunHooks()), Mock()
        solver.solve.return_value = 'abc12'
        http.get.side_effect = [FakeResponse(f'<meta name="csrf-token" content="token-{n}">') for n in (1, 2)]
        http.post.return_value = FakeResponse(json_payload={'code': 'CAPTCHA_INVALID'})
        with patch('gdt_tax.auth.fetch_captcha', return_value=b'synthetic'), patch('gdt_tax.auth.time.sleep'):
            with self.assertRaises(AuthFailure) as caught:
                auth.login(http, solver, settings)
        self.assertEqual(caught.exception.outcome, AuthOutcome.CAPTCHA_INVALID)
        self.assertEqual([c.kwargs['headers']['X-XSRF-TOKEN'] for c in http.post.call_args_list], ['token-1', 'token-2'])
        self.assertEqual(solver.rejected.call_count, 2)

    def test_legacy_retry_uses_latest_form_and_cancellation_stays_cancellation(self):
        settings = Mock(login_attempts=2, username='synthetic', password='fixture')
        portal = EtaxLegacyPortal(Mock(), Mock(), settings)
        portal.captcha.solve.return_value = 'abc12'
        first = FakeResponse(LOGIN_PAGE_HTML, url='https://fixture.test/1')
        rotated = FakeResponse(LOGIN_PAGE_HTML.replace('SESS01', 'ROTATED') + '<div>CAPTCHA không đúng</div>', url='https://fixture.test/2')
        with patch.object(portal, '_legacy_captcha_image', return_value=b'fixture'), patch.object(portal, '_post_form', side_effect=[rotated, FakeResponse(LOGIN_OK_HTML)]) as submit:
            portal._submit_login(first)
        self.assertIn('ROTATED', submit.call_args.args[0])
        self.assertEqual(submit.call_args.args[2], rotated.url)
        portal.captcha.solve.side_effect = RunCancelled()
        with patch.object(portal, '_legacy_captcha_image', return_value=b'fixture'):
            with self.assertRaises(RunCancelled):
                portal._submit_login(first)

    def test_live_dvc_desc_captcha_rejection_retries_then_accepts(self):
        settings = Settings.from_env(environ={}, env_file=None, username='synthetic', password='fixture', login_attempts=2)
        http, solver = Mock(hooks=RunHooks()), Mock()
        solver.solve.return_value = 'abc12'
        http.get.side_effect = [FakeResponse(f'<meta name="csrf-token" content="token-{n}">') for n in (1, 2)]
        http.post.side_effect = [FakeResponse(json_payload={'status': '999', 'desc': 'Mã captcha không đúng, vui lòng thử lại.'}),
                                 FakeResponse(json_payload={'status': '200'})]
        with patch('gdt_tax.auth.fetch_captcha', return_value=b'synthetic'), patch('gdt_tax.auth.time.sleep'):
            self.assertTrue(auth.login(http, solver, settings))
        self.assertEqual(http.post.call_count, 2)
        solver.rejected.assert_called_once()
        solver.accepted.assert_called_once()
        self.assertEqual([c.kwargs['headers']['X-XSRF-TOKEN'] for c in http.post.call_args_list], ['token-1', 'token-2'])
        for desc in ('Unreviewed response', None, {'status': '200'}):
            self.assertEqual(classify_response(FakeResponse(json_payload={'status': '999', 'desc': desc}), 'DVC'), AuthOutcome.SCHEMA_UNKNOWN)

    def test_cli_and_desktop_share_auth_code_before_pipeline_starts(self):
        failure = AuthFailure(AuthOutcome.INVALID_CREDENTIALS)
        with temporary_directory() as directory:
            config = RunConfig('login', Path(directory), username='synthetic', password='fixture')
            manager = ETaxSessionManager()
            with patch.object(manager, 'ensure_authenticated', side_effect=failure):
                result = manager.execute(config, RunHooks(), Mock())
            self.assertEqual(result.error_code, failure.code)
            with patch('gdt_tax.cli.Settings.from_env', return_value=config.settings()), patch('gdt_tax.cli.create_solver'), patch('gdt_tax.cli.HttpClient'), patch('gdt_tax.cli.Pipeline') as pipeline:
                pipeline.return_value.run.side_effect = failure
                with self.assertLogs('gdt_tax', logging.ERROR) as logs:
                    code = cli.main(['--log-file', ''])
            self.assertEqual(code, cli.EXIT_INCOMPLETE)
            self.assertIn(result.error_code, ' '.join(logs.output))

    def test_matrix_provenance_is_explicitly_synthetic(self):
        manifest = json.loads((Path(__file__).parent / 'fixtures/auth/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(set(manifest['outcomes']), {o.value for o in AuthOutcome})
        self.assertEqual(manifest['provenance'], 'synthetic')

