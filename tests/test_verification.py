"""Access verification must stop authentication without consuming five OCR retries."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from gdt_tax.errors import LegacyEtaxError, PortalVerificationError
from gdt_tax.portals.etax_legacy import EtaxLegacyPortal
from tests.support import FakeResponse
from tests.test_etax_legacy import LOGIN_OK_HTML, LOGIN_PAGE_HTML
from tests.test_http import StubResponse, make_client

CHALLENGE = (
    '<html><apm_do_not_touch><script>var privateValue="private-fixture";</script></apm_do_not_touch>'
    '<body>This question is for testing whether you are a human visitor.'
    '<input id="ans" name="answer"><button id="jar">Submit</button>'
    'Your support ID is: private-support-id.</body></html>'
)


class VerificationTests(unittest.TestCase):
    def test_visible_bad_credentials_stop_without_ocr_rejection_or_retry(self):
        portal = EtaxLegacyPortal(Mock(), Mock(), Mock(login_attempts=10))
        portal.captcha.solve.return_value = 'abc12'
        failure = FakeResponse(LOGIN_PAGE_HTML + '<div>Tên đăng nhập hoặc mật khẩu của bạn không chính xác!</div>')
        with patch.object(portal, '_legacy_captcha_image', return_value=b'fixture'), patch.object(portal, '_post_form', return_value=failure) as post:
            with self.assertRaisesRegex(LegacyEtaxError, 'mật khẩu không chính xác'):
                portal._submit_login(FakeResponse(LOGIN_PAGE_HTML))
        post.assert_called_once()
        portal.captcha.solve.assert_called_once()
        portal.captcha.rejected.assert_not_called()
        portal.captcha.accepted.assert_not_called()

    def test_static_credential_error_does_not_stop_captcha_retry(self):
        portal = EtaxLegacyPortal(Mock(), Mock(), Mock(login_attempts=2))
        portal.captcha.solve.return_value = 'abc12'
        failure = FakeResponse(LOGIN_PAGE_HTML + '<div>CAPTCHA không đúng</div><script>function unused(){alert("Tên đăng nhập hoặc mật khẩu của bạn không chính xác!");}</script>')
        success = FakeResponse(LOGIN_OK_HTML)
        with patch.object(portal, '_legacy_captcha_image', return_value=b'fixture'), patch.object(portal, '_post_form', side_effect=[failure, success]):
            self.assertIs(portal._submit_login(FakeResponse(LOGIN_PAGE_HTML)), success)
        portal.captcha.rejected.assert_called_once()
        portal.captcha.accepted.assert_called_once()

    def test_http_200_challenge_is_not_retried_and_does_not_echo_page(self):
        client, session = make_client([StubResponse(200, text=CHALLENGE)], retries=3)
        with self.assertRaises(PortalVerificationError) as caught:
            client.post('/Request', data={'_password': 'private-password'})
        self.assertEqual(len(session.calls), 1)
        self.assertIn('xác minh trình duyệt', str(caught.exception))
        for secret in ['private-fixture', 'private-support-id', 'private-password']:
            self.assertNotIn(secret, str(caught.exception))

    def test_protected_normal_page_with_unexecuted_challenge_script_is_allowed(self):
        template = CHALLENGE.replace('</script>', '<\\/script>')
        text = ('<html><apm_do_not_touch><script>var template=' + repr(template) + ';</script>'
                '</apm_do_not_touch><noscript>Please enable JavaScript. Your support ID is: fixture.</noscript>'
                '<form id="loginForm"><input name="_userName"></form></html>')
        client, session = make_client([StubResponse(200, text=text)])
        self.assertEqual(client.get('/Request').status_code, 200)
        self.assertEqual(len(session.calls), 1)

    def test_http_403_rejected_page_is_reported_as_access_verification(self):
        client, _ = make_client([StubResponse(403, text=(
            '<html><body>The requested URL was rejected. '
            'Please consult with your administrator. Your support ID is: fixture.</body></html>'))])
        with self.assertRaises(PortalVerificationError):
            client.get('/Request')

    def test_legacy_does_not_report_ocr_rejection_for_access_challenge(self):
        client, session = make_client([StubResponse(200, text=CHALLENGE)])
        solver = Mock()
        solver.solve.return_value = 'abc12'
        portal = EtaxLegacyPortal(client, solver, Mock(username='fixture', password='fixture', header_profile='browser', login_attempts=10))
        with patch.object(portal, '_legacy_captcha_image', return_value=b'fixture'):
            with self.assertRaises(PortalVerificationError):
                portal._submit_login(FakeResponse(LOGIN_PAGE_HTML, url='https://fixture.test/Request'))
        self.assertEqual(len(session.calls), 1)
        solver.solve.assert_called_once()
        solver.rejected.assert_not_called()
        solver.accepted.assert_not_called()

    def test_initial_legacy_challenge_never_starts_ocr(self):
        client, session = make_client([StubResponse(200, text=CHALLENGE)])
        solver = Mock()
        portal = EtaxLegacyPortal(client, solver, Mock(login_attempts=10, header_profile='browser'))
        with self.assertRaises(PortalVerificationError):
            portal.login()
        self.assertEqual(len(session.calls), 1)
        solver.solve.assert_not_called()

    def test_login_post_is_document_navigation_and_other_posts_keep_xhr(self):
        http = Mock()
        portal = EtaxLegacyPortal(http, Mock(), Mock(header_profile='browser'))
        for operation, destination, mode in [('corpUserLoginProc', 'document', 'navigate'),
                                              ('tracuuTBThueKhacProc', 'empty', 'cors')]:
            portal._post_fields('https://fixture.test/Request', {'dse_operationName': operation}, 'https://fixture.test/login')
            headers = http.post.call_args.kwargs['headers']
            self.assertEqual(headers['Sec-Fetch-Dest'], destination)
            self.assertEqual(headers['Sec-Fetch-Mode'], mode)
            self.assertEqual(headers['Referer'], 'https://fixture.test/login')
            self.assertEqual(headers['Content-Type'], 'application/x-www-form-urlencoded')

    def test_login_does_not_log_static_validators_or_misread_script_form_name(self):
        portal = EtaxLegacyPortal(Mock(), Mock(), Mock(login_attempts=2))
        portal.captcha.solve.return_value = 'abc12'
        failure = FakeResponse(LOGIN_PAGE_HTML + '<div>CAPTCHA không đúng</div><script>function validate(){alert("Bạn chưa nhập Mật khẩu!");}</script>')
        success = FakeResponse(LOGIN_OK_HTML + '<script>var priorForm="loginForm";</script>')
        with patch.object(portal, '_legacy_captcha_image', return_value=b'fixture'), patch.object(portal, '_post_form', side_effect=[failure, success]):
            with self.assertLogs(portal.logger, level='INFO') as captured:
                self.assertIs(portal._submit_login(FakeResponse(LOGIN_PAGE_HTML)), success)
        self.assertNotIn('Bạn chưa nhập', '\n'.join(captured.output))
        portal.captcha.accepted.assert_called_once()
