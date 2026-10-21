"""Conservative adapter-specific authentication evidence; never echo portal text."""
from __future__ import annotations

import re
from enum import Enum
from html import unescape
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup

from .errors import LegacyEtaxError, LoginError, PortalVerificationError
from .verification import raise_for_portal_verification


class AuthOutcome(str, Enum):
    SUCCESS = 'SUCCESS'
    INVALID_CREDENTIALS = 'INVALID_CREDENTIALS'
    CAPTCHA_INVALID = 'CAPTCHA_INVALID'
    EXPIRED_SESSION = 'EXPIRED_SESSION'
    ACCESS_VERIFICATION = 'ACCESS_VERIFICATION'
    MAINTENANCE = 'MAINTENANCE'
    INTERACTIVE_AUTH_REQUIRED = 'INTERACTIVE_AUTH_REQUIRED'
    SCHEMA_UNKNOWN = 'SCHEMA_UNKNOWN'


MESSAGES = {
    AuthOutcome.INVALID_CREDENTIALS: 'Tên đăng nhập hoặc mật khẩu không chính xác; kiểm tra tài khoản rồi thử lại.',
    AuthOutcome.CAPTCHA_INVALID: 'Cổng xác nhận CAPTCHA không đúng.',
    AuthOutcome.EXPIRED_SESSION: 'Phiên đăng nhập đã hết hạn.',
    AuthOutcome.ACCESS_VERIFICATION: 'Cổng yêu cầu xác minh trình duyệt; mở cổng để kiểm tra.',
    AuthOutcome.MAINTENANCE: 'Cổng đang bảo trì hoặc tạm thời không phục vụ; thử lại sau.',
    AuthOutcome.INTERACTIVE_AUTH_REQUIRED: 'Cổng yêu cầu OTP/SSO; cần xác thực tương tác bằng luồng được hỗ trợ.',
    AuthOutcome.SCHEMA_UNKNOWN: 'Phản hồi xác thực chưa được nhận diện; đã dừng thử đăng nhập.',
}


class AuthFailure(LoginError, LegacyEtaxError):
    def __init__(self, outcome: AuthOutcome):
        self.outcome = outcome
        self.code = 'AUTH_' + outcome.value
        super().__init__(self.code + ': ' + MESSAGES[outcome])


def classify_response(response, adapter: str, *, phase='login_submit', authenticated=False) -> AuthOutcome:
    if adapter not in {'DVC', 'ETAX_LEGACY'}:
        return AuthOutcome.SCHEMA_UNKNOWN
    body = getattr(response, 'content', b'') or b''
    if len(body) > 2 * 1024 * 1024:
        return AuthOutcome.SCHEMA_UNKNOWN
    try:
        raise_for_portal_verification(response)
    except PortalVerificationError:
        return AuthOutcome.ACCESS_VERIFICATION
    if response.status_code in {502, 503, 504}:
        return AuthOutcome.MAINTENANCE
    text = getattr(response, 'text', '') or ''
    try:
        payload = response.json()
    except (ValueError, AttributeError):
        payload = None
    json_message = ''
    if isinstance(payload, dict):
        code = payload.get('code', payload.get('errorCode', ''))
        explicit = {'INVALID_CREDENTIALS': AuthOutcome.INVALID_CREDENTIALS,
                    'CAPTCHA_INVALID': AuthOutcome.CAPTCHA_INVALID, 'INVALID_CAPTCHA': AuthOutcome.CAPTCHA_INVALID,
                    'SESSION_EXPIRED': AuthOutcome.EXPIRED_SESSION, 'MAINTENANCE': AuthOutcome.MAINTENANCE,
                    'OTP_REQUIRED': AuthOutcome.INTERACTIVE_AUTH_REQUIRED, 'SSO_REQUIRED': AuthOutcome.INTERACTIVE_AUTH_REQUIRED}
        if isinstance(code, str) and code in explicit:
            return explicit[code]
        json_message = ' '.join(str(payload[key]) for key in ('message', 'error', 'description', 'desc')
                                if isinstance(payload.get(key), str))
    if body.lstrip().startswith((b'<?xml', b'%PDF-', b'PK')):
        if authenticated and response.status_code == 401:
            return AuthOutcome.EXPIRED_SESSION
        # Downloaded business documents are not authentication pages. In
        # particular, do not scan XML notice text for credential/CAPTCHA errors.
        if not body.lstrip().startswith(b'<?xml'):
            return AuthOutcome.SCHEMA_UNKNOWN
        from .xml_policy import XmlReadError, parse_xml
        try:
            from lxml import etree
            if etree.QName(parse_xml(body)).localname.casefold() != 'html':
                return AuthOutcome.SCHEMA_UNKNOWN
        except XmlReadError:
            return AuthOutcome.SCHEMA_UNKNOWN
    soup = BeautifulSoup(text if not isinstance(payload, dict) else '', 'html.parser')
    login_form = soup.select_one('form#loginForm, form[name="loginForm"]') is not None
    home_form = soup.select_one('form#goProcForm, form[name="goProcForm"]') is not None
    # A selector returns a snapshot: decompose() on a parent also destroys its
    # descendants. Visit children first so nested matches retain their attrs.
    for node in reversed(soup(['script', 'style', 'noscript', 'template'])):
        node.decompose()
    for node in reversed(soup.select('[hidden], [aria-hidden="true"], input[type="hidden"]')):
        node.decompose()
    for node in reversed(soup.select('[style]')):
        style = ''.join(str(node.get('style', '')).casefold().split())
        if 'display:none' in style or 'visibility:hidden' in style:
            node.decompose()
    visible = ' '.join((soup.get_text(' ', strip=True) + ' ' + json_message).casefold().split())
    patterns = {
        AuthOutcome.INVALID_CREDENTIALS: ('tên đăng nhập hoặc mật khẩu của bạn không chính xác',
            'tên đăng nhập hoặc mật khẩu không chính xác', 'tên đăng nhập hoặc mật khẩu không đúng',
            'sai tên đăng nhập hoặc mật khẩu', 'invalid credentials'),
        AuthOutcome.CAPTCHA_INVALID: ('captcha không đúng', 'captcha không chính xác', 'mã xác nhận không đúng',
            'mã xác thực không đúng', 'mã xác nhận không chính xác', 'mã xác thực không chính xác',
            'sai mã captcha', 'invalid captcha'),
        AuthOutcome.MAINTENANCE: ('hệ thống đang bảo trì', 'cổng đang bảo trì', 'under maintenance'),
        AuthOutcome.INTERACTIVE_AUTH_REQUIRED: ('yêu cầu xác thực otp', 'nhập mã otp', 'otp required', 'sso required'),
        AuthOutcome.EXPIRED_SESSION: ('phiên giao dịch đã hết', 'phiên làm việc đã hết', 'session expired',
            'session đã hết hạn'),
    }
    for outcome, markers in patterns.items():
        if any(marker in visible for marker in markers):
            return outcome
    if soup.select_one('input[autocomplete="one-time-code"], form#otpForm, form#ssoForm'):
        return AuthOutcome.INTERACTIVE_AUTH_REQUIRED
    url = urlsplit(urljoin(getattr(response, 'url', '') or '',
                          response.headers.get('Location', '') if response.status_code in {301, 302, 303, 307, 308} else ''))
    events = parse_qs(url.query)
    at_login = (url.path.rstrip('/').endswith('/login')
                or events.get('dse_nextEventName', events.get('nextEventName')) == ['login'])
    if authenticated and (response.status_code == 401 or login_form or at_login):
        return AuthOutcome.EXPIRED_SESSION
    if phase == 'login_submit' and 200 <= response.status_code < 300:
        if adapter == 'DVC' and isinstance(payload, dict) and str(payload.get('status')) == '200':
            return AuthOutcome.SUCCESS
        # Legacy's reviewed navigation marker is in JavaScript; it is never
        # considered an error message or a signal that the session expired.
        home_operation = re.search(r'''[?&]dse_operationName=corporateHomeProc(?:[&'"\s<>]|$)''', unescape(text))
        if adapter == 'ETAX_LEGACY' and home_form and home_operation and not login_form:
            return AuthOutcome.SUCCESS
    return AuthOutcome.SCHEMA_UNKNOWN


def raise_terminal(response, adapter: str, *, phase='page', authenticated=False) -> None:
    outcome = classify_response(response, adapter, phase=phase, authenticated=authenticated)
    if outcome == AuthOutcome.EXPIRED_SESSION:
        from .legacy_session import SessionExpired
        raise SessionExpired()
    if outcome in {AuthOutcome.ACCESS_VERIFICATION, AuthOutcome.MAINTENANCE,
                   AuthOutcome.INTERACTIVE_AUTH_REQUIRED, AuthOutcome.INVALID_CREDENTIALS}:
        raise AuthFailure(outcome)
