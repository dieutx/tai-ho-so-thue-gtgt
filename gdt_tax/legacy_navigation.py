"""Business adapters compose session navigation; no declaration search inheritance."""
from __future__ import annotations

from .portals.etax_legacy import LegacySessionNavigator, _form_fields


def form_fields(html: str, form_id: str):
    return _form_fields(html, form_id)


class LegacyBusinessPortal:
    def __init__(self, http, captcha, settings, logger=None, *, login_attempts=None,
                 session_state=None, navigator: LegacySessionNavigator | None = None):
        self.navigator = navigator or LegacySessionNavigator(http, captcha, settings, logger,
            login_attempts=login_attempts, session_state=session_state)
        self.http, self.captcha, self.settings = http, captcha, settings
        self.logger = self.navigator.logger
        self._search_page_html = ''
        self._search_page_url = ''
        self._search_form_id = ''

    @property
    def profile(self):
        return self.navigator.profile

    @property
    def session_state(self):
        return self.navigator.session_state

    @property
    def _logged_in(self):
        return self.navigator._logged_in

    @property
    def dse_session_id(self):
        return self.navigator.dse_session_id

    @dse_session_id.setter
    def dse_session_id(self, value):
        self.navigator.dse_session_id = value

    @property
    def home_page_id(self):
        return self.navigator.home_page_id

    @home_page_id.setter
    def home_page_id(self, value):
        self.navigator.home_page_id = value

    def login(self):
        return self.navigator.login()

    def _open_operation_page(self, operation, expected_form, label):
        return self.navigator._open_operation_page(operation, expected_form, label)

    def _post_form(self, html, form_id, referer, overrides):
        return self.navigator._post_form(html, form_id, referer, overrides)

    def _form_id_for_operation(self, html, operation, expected):
        return self.navigator._form_id_for_operation(html, operation, expected)
