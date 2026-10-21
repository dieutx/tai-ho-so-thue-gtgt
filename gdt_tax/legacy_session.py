"""Optional DSE authentication state shared by serialized embedded operations."""
from __future__ import annotations

from dataclasses import dataclass, field

from .auth_outcomes import AuthFailure, AuthOutcome


@dataclass
class LegacySessionState:
    dse_session_id: str = field(default="", repr=False)
    home_page_id: str = field(default="", repr=False)
    #: Trang chủ doanh nghiệp đã đăng nhập; giữ lại để mở thẳng trang nghiệp vụ
    #: bằng đúng liên kết/mã trang mà cổng phát cho phiên này.
    home_page_html: str = field(default="", repr=False)
    authenticated: bool = False

    def clear(self) -> None:
        self.dse_session_id = self.home_page_id = self.home_page_html = ""
        self.authenticated = False


class SessionExpired(AuthFailure):
    """An actual authentication response; distinct from HTML/parser/server errors."""
    def __init__(self, message=''):
        super().__init__(AuthOutcome.EXPIRED_SESSION)
