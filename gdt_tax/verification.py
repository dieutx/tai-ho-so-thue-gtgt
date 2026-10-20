"""Recognize access verification pages without treating them as tax CAPTCHA failures."""
from __future__ import annotations

from bs4 import BeautifulSoup

from .errors import PortalVerificationError

VERIFICATION_MESSAGE = (
    'Cổng Thuế đang yêu cầu xác minh trình duyệt từ hệ thống bảo vệ truy cập. '
    'Đã dừng để tránh thử CAPTCHA đăng nhập liên tục. '
    'Mở cổng Thuế bằng trình duyệt để kiểm tra yêu cầu xác minh; '
    'ứng dụng chưa thể tiếp tục phiên này.'
)


def raise_for_portal_verification(response) -> None:
    body = getattr(response, 'content', b'') or b''
    if len(body) > 2 * 1024 * 1024:
        return
    text = getattr(response, 'text', '') or ''
    lower = text.lower()
    if 'apm_do_not_touch' not in lower and 'your support id is' not in lower:
        return
    soup = BeautifulSoup(text, 'html.parser')
    for node in soup(['script', 'style', 'noscript']):
        node.decompose()
    visible = soup.get_text(' ', strip=True).lower()
    captcha = (soup.find('input', attrs={'name': 'answer', 'id': 'ans'}) is not None
               and soup.find('button', id='jar') is not None
               and 'human visitor' in visible)
    rejected = ('your support id is' in visible
                and ('the requested url was rejected' in visible or 'request rejected' in visible))
    if captcha or rejected:
        raise PortalVerificationError(VERIFICATION_MESSAGE)
