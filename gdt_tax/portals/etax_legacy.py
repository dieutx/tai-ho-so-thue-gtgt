"""Nguồn Thuế điện tử cũ — ``thuedientu.gdt.gov.vn``.

Một số tờ khai nộp trước mốc chuyển nguồn chỉ còn hiển thị trên trang Thuế điện
tử cũ, không tra cứu được qua Cổng Dịch vụ công. Trang này dùng chung tài khoản
với DVC nhưng là một máy chủ khác, với luồng DSE khác hẳn::

    EstablishSession → corpIndexProc → loginForm + CAPTCHA
      → corporateHomeProc → corpHomePageProc
      → traCuuToKhaiProc/query (tối đa 31 ngày, 10 bản ghi mỗi trang)
      → downTkhai&messageId=... → file XML tờ khai

Hai lớp trong module này:

* :class:`EtaxLegacyPortal` — portal thật, tự đăng nhập trang cũ và trả hồ sơ
  theo :class:`CaseRecord` như mọi portal khác.
* :class:`EtaxLegacyFallback` — bọc một portal gốc (DVC/ETAX): tra cứu qua portal
  gốc như thường, nhưng khi đoạn ngày **trước mốc** ``etax_cutoff`` mà cổng
  không trả hồ sơ nào thì hỏi thêm trang cũ.
"""

from __future__ import annotations

import logging
import re
import time
import zipfile
from collections.abc import Mapping
from html import unescape
from io import BytesIO
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from ..auth_outcomes import AuthFailure, AuthOutcome, classify_response, raise_terminal
from ..constants import LEGACY_ETAX_BASE, LEGACY_ETAX_ORIGIN, SOURCE_ETAX_LEGACY
from ..contracts import DownloadArtifact
from ..errors import LegacyEtaxError, LegacyPageError
from ..headers import build_image_headers, build_page_headers, build_xhr_headers
from ..http import HttpClient
from ..legacy_session import LegacySessionState
from ..models import CaseRecord, PageResult, SearchPeriod
from ..naming import safe_filename_part
from ..parsing import parse_record_table
from .base import Portal

#: Thành công khi trang trả về luồng trang chủ doanh nghiệp.
_LOGIN_OK_MARKER = "corporateHomeProc"
#: Trang cũ trả lại form đăng nhập khi sai mã CAPTCHA hoặc hết phiên.
_LOGIN_FORM_ID = "loginForm"
_SEARCH_FORM_ID = "traCuuKhaiForm"
_RESULT_TABLE_ID = "data_content_onday"

_LEGACY_ALERT_RE = re.compile(r"alert\(\s*['\"](.*?)['\"]\s*\)", re.I | re.S)


def _alerts(html: str) -> list[str]:
    """Các câu thông báo mà trang cũ nhúng trong ``alert('...')``."""
    messages = []
    for match in _LEGACY_ALERT_RE.finditer(html):
        text = re.sub(r"\s+", " ", match.group(1)).strip()
        if text:
            messages.append(text)
    return messages


def _form_node(html: str, form_id: str):
    """Tìm form theo ``id`` rồi tới ``name`` (một số màn hình legacy chỉ có name)."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id=form_id) if form_id else None
    if form is None and form_id:
        form = soup.find("form", attrs={"name": form_id})
    return form


def _credentials_rejected(html: str) -> bool:
    """Only recognize displayed server errors, never validator JavaScript."""
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup(['script', 'style', 'noscript', 'template']):
        node.decompose()
    visible = ' '.join(soup.stripped_strings).casefold()
    return any(message in visible for message in (
        'tên đăng nhập hoặc mật khẩu của bạn không chính xác',
        'tên đăng nhập hoặc mật khẩu không đúng',
        'sai tên đăng nhập hoặc mật khẩu',
    ))


def _form_data(form) -> tuple[str, dict[str, str]]:
    """Action URL và toàn bộ ô input có tên của một form đã tìm thấy."""
    action = str(form.get("action") or "/etaxnnt/Request")
    data: dict[str, str] = {}
    for field in form.find_all("input"):
        name = field.get("name")
        if name:
            data[str(name)] = str(field.get("value") or "")
    return urljoin(f"{LEGACY_ETAX_BASE}/", action), data


def _form_fields(html: str, form_id: str) -> tuple[str, dict[str, str]]:
    """Action URL và toàn bộ ô input có tên của một form trong trang legacy."""
    form = _form_node(html, form_id)
    if form is None:
        raise LegacyEtaxError(f"Không tìm thấy form id={form_id!r} trên trang legacy")
    return _form_data(form)


def _operation_url(html: str, operation: str) -> str:
    """URL ``/etaxnnt/Request`` có ``dse_operationName=<operation>`` nếu trang chủ có link."""
    if not html or operation not in html:
        return ""
    decoded = unescape(html)
    pattern = r"(?:https?://[^\s'\"<>]+|/etaxnnt/Request\?[^\s'\"<>]+)"
    for match in re.finditer(pattern, decoded):
        value = match.group(0)
        if f"dse_operationName={operation}" in value and "dse_sessionId=" in value:
            return urljoin(f"{LEGACY_ETAX_BASE}/", value)
    return ""


def _page_detail(response) -> str:
    """Câu ngắn cổng trả về (title/alert/chữ hiển thị) để lỗi có ngữ cảnh."""
    text = getattr(response, "text", "") or ""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    for node in soup(["script", "style"]):
        node.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    visible = " ".join(soup.stripped_strings)
    detail = title or next(iter(_alerts(text)), "") or visible
    return re.sub(r"\s+", " ", detail).strip()[:180]


def _js_redirect(html: str, required_text: str) -> str:
    """URL mà trang legacy tự chuyển hướng bằng JavaScript."""
    candidates: list[str] = []
    for pattern in (
        r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]",
        r"['\"]((?:https?://[^'\"]+|/etaxnnt/Request\?[^'\"]+))['\"]",
    ):
        candidates.extend(unescape(match.group(1)) for match in re.finditer(pattern, html, re.I))
    for value in candidates:
        if required_text in value:
            return urljoin(f"{LEGACY_ETAX_BASE}/", value)
    raise LegacyEtaxError(f"Không tìm thấy URL chuyển hướng chứa {required_text!r}")


def _find_operation_url(html: str, operation: str) -> str:
    """Tìm URL ``/etaxnnt/Request`` có ``dse_operationName=<operation>``."""
    decoded = unescape(html)
    pattern = rf"/etaxnnt/Request\?[^'\"<>]*dse_operationName={re.escape(operation)}[^'\"<>]*"
    match = re.search(pattern, decoded, re.I)
    if match:
        return urljoin(f"{LEGACY_ETAX_BASE}/", match.group(0))
    raise LegacyEtaxError(f"Không tìm thấy URL operation={operation}")


def _query_parameter(url: str, name: str) -> str:
    values = parse_qs(urlparse(url).query).get(name)
    return values[0] if values else ""


def _total_pages(html: str) -> int:
    """Tổng số trang theo dòng ``Trang 1/ 5 . Có 43 bản ghi`` của trang legacy."""
    text = " ".join(BeautifulSoup(html, "html.parser").stripped_strings)
    match = re.search(r"Trang\s*\d+\s*/\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1))
    return 1 if _RESULT_TABLE_ID in html else 0


class EtaxLegacyPortal(Portal):
    """Tra cứu và tải tờ khai trên trang Thuế điện tử cũ.

    Luồng DSE khác hẳn DVC nhưng kết quả vẫn là :class:`PageResult` /
    :class:`CaseRecord` nên pipeline dùng chung được. Trang cũ trả **XML**
    (không phải ZIP): :meth:`download` gói XML vào ZIP trong bộ nhớ để phần lưu
    file và metadata dùng chung mà không phải sửa gì.
    """

    source = SOURCE_ETAX_LEGACY
    detail_loai = SOURCE_ETAX_LEGACY
    #: Trang legacy không dùng CSRF token khi tải.
    csrf_optional = True

    def __init__(
        self,
        http: HttpClient,
        captcha,
        settings,
        logger: logging.Logger | None = None,
        *,
        login_attempts: int | None = None,
        session_state: LegacySessionState | None = None,
    ) -> None:
        super().__init__(http, captcha, settings, logger)
        self.login_attempts = (
            login_attempts if login_attempts is not None else settings.login_attempts
        )
        self.dse_session_id = ""
        self.home_page_id = ""
        self.home_page_html = ""
        self._search_page_html = ""
        self._search_page_url = ""
        #: Form thực tế của trang nghiệp vụ; cổng có lúc đổi id/name của form.
        self._search_form_id = _SEARCH_FORM_ID
        self._logged_in = False
        self.session_state = session_state

    # --- Đăng nhập trang cũ ---
    def login(self) -> None:
        """Đăng nhập trang Thuế điện tử cũ; thành công thì mới tra cứu được."""
        if self.session_state is not None and self.session_state.authenticated:
            self.dse_session_id = self.session_state.dse_session_id
            self.home_page_id = self.session_state.home_page_id
            self.home_page_html = self.session_state.home_page_html
            self._logged_in = True
            return
        if self._logged_in and self.session_state is None:
            return

        establish = f"{LEGACY_ETAX_BASE}/EstablishSession"
        response = self.http.get(
            establish,
            params={
                "fromOpName": "corpIndexProc",
                "fromStateName": "initial",
                "fromEventName": "start",
            },
            headers=build_page_headers(profile=self.profile, site="none"),
        )
        raise_terminal(response, 'ETAX_LEGACY')
        if response.status_code != 200:
            raise LegacyEtaxError(f"Mở EstablishSession lỗi HTTP {response.status_code}")
        first_url = _js_redirect(response.text, "dse_sessionId=")
        self.dse_session_id = _query_parameter(first_url, "dse_sessionId")
        if not self.dse_session_id:
            raise LegacyEtaxError("Không lấy được dse_sessionId từ trang legacy")

        response = self.http.get(
            first_url,
            headers=build_page_headers(profile=self.profile, headers={"Referer": establish}),
        )
        response = self._post_form(
            response.text, "goProcForm", response.url,
            {"dse_operationName": "corpIndexProc", "dse_nextEventName": "home"},
        )
        response = self._post_form(
            response.text, "goProcForm", response.url,
            {"dse_operationName": "corpIndexProc", "dse_nextEventName": "loginOptions"},
        )

        try:
            login_url = _js_redirect(response.text, "dse_nextEventName=login")
        except LegacyEtaxError:
            _, fields = _form_fields(response.text, "goProcForm")
            fields.update({"dse_operationName": "corpIndexProc", "dse_nextEventName": "login"})
            login_url = f"{LEGACY_ETAX_BASE}/Request?{urlencode(fields)}"

        response = self.http.get(
            login_url,
            headers=build_page_headers(profile=self.profile, headers={"Referer": response.url}),
        )
        raise_terminal(response, 'ETAX_LEGACY')
        if response.status_code != 200 or _form_node(response.text, _LOGIN_FORM_ID) is None:
            raise LegacyEtaxError("Trang legacy không trả về form đăng nhập")

        ok_response = self._submit_login(response)
        self._open_home_page(ok_response)
        self._logged_in = True
        if self.session_state is not None:
            self.session_state.dse_session_id = self.dse_session_id
            self.session_state.home_page_id = self.home_page_id
            self.session_state.home_page_html = self.home_page_html
            self.session_state.authenticated = True
        self.logger.info("ĐĂNG NHẬP legacy THÀNH CÔNG")

    def _submit_login(self, login_page):
        """Gửi tên đăng nhập/mật khẩu/CAPTCHA, thử lại khi đọc sai mã."""
        last_message = "không rõ"
        last_outcome = AuthOutcome.SCHEMA_UNKNOWN
        for attempt in range(1, self.login_attempts + 1):
            hooks = getattr(self.http, "hooks", None)
            if hooks is not None and hooks.budget is not None:
                hooks.budget.authenticate()
            image = self._legacy_captcha_image(login_page.url)
            code = self.captcha.solve(image) if image else ""
            if not code:
                last_message = "không đọc được CAPTCHA"
                self.logger.warning("Legacy: %s (lần %s)", last_message, attempt)
                continue
            response = self._post_form(
                login_page.text, _LOGIN_FORM_ID, login_page.url,
                {
                    "dse_operationName": "corpUserLoginProc",
                    "dse_processorState": "initial",
                    "dse_nextEventName": "start",
                    "showVerifyCode": "show",
                    "_userName": self.settings.username,
                    "_password": self.settings.password,
                    "login_type": "01",
                    "_verifyCode": code,
                },
            )
            outcome = classify_response(response, 'ETAX_LEGACY')
            last_outcome = outcome
            # Script alert strings include unexecuted empty-field validators.
            # They are not server-side authentication errors.
            if outcome == AuthOutcome.SUCCESS:
                accepted = getattr(self.captcha, "accepted", None)
                if callable(accepted):
                    accepted()
                return response
            if outcome != AuthOutcome.CAPTCHA_INVALID:
                raise AuthFailure(outcome)
            rejected = getattr(self.captcha, "rejected", None)
            if callable(rejected):
                rejected()
            last_message = "tên đăng nhập/mật khẩu/CAPTCHA không được chấp nhận"
            self.logger.warning("Legacy: đăng nhập chưa được (lần %s/%s)", attempt, self.login_attempts)
            # A rejected login can rotate DSE hidden fields and the form action.
            # The next image and POST must belong to the latest login page.
            if _form_node(response.text, _LOGIN_FORM_ID) is not None:
                login_page = response
        raise AuthFailure(last_outcome)

    def _open_home_page(self, login_result) -> None:
        """Đi qua ``corporateHomeProc`` để lấy ``dse_pageId`` của trang chủ."""
        response = self._post_form(
            login_result.text, "goProcForm", login_result.url,
            {
                "dse_operationName": "corporateHomeProc",
                "dse_processorState": "initial",
                "dse_nextEventName": "start",
            },
        )
        home_url = _find_operation_url(response.text, "corpHomePageProc")
        home = self.http.get(home_url, headers=build_page_headers(profile=self.profile))
        self.home_page_html = home.text
        self.home_page_id = _query_parameter(home_url, "dse_pageId")
        if not self.home_page_id:
            raise LegacyEtaxError("Không lấy được dse_pageId của trang chủ legacy")

    def _legacy_captcha_image(self, referer: str) -> bytes | None:
        response = self.http.get(
            f"{LEGACY_ETAX_BASE}/servlet/ImageServlet",
            params={"d": int(time.time() * 1000)},
            headers=build_image_headers(profile=self.profile, headers={"Referer": referer}),
        )
        content_type = response.headers.get("content-type", "").lower()
        if response.status_code == 200 and "image" in content_type and len(response.content) > 100:
            return response.content
        self.logger.error(
            "CAPTCHA legacy lỗi: HTTP=%s content-type=%s", response.status_code, content_type or "?"
        )
        return None

    def _post_form(self, html: str, form_id: str, referer: str, overrides: Mapping[str, Any]):
        action, fields = _form_fields(html, form_id)
        fields.update({key: str(value) for key, value in overrides.items()})
        return self._post_fields(action, fields, referer)

    def _post_fields(self, action: str, fields: Mapping[str, Any], referer: str):
        """POST form đăng nhập điều hướng trang; nghiệp vụ legacy dùng XHR."""
        # loginForm's logon()/checkVerify() calls native form.submit().
        # Its POST navigates the document; other legacy operations remain XHR.
        navigation = fields.get('dse_operationName') == 'corpUserLoginProc'
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': LEGACY_ETAX_ORIGIN,
            'Referer': referer,
        }
        response = self.http.post(
            action,
            data={key: str(value) for key, value in fields.items()},
            headers=build_page_headers(profile=self.profile, headers=headers) if navigation else build_xhr_headers(
                profile=self.profile,
                accept="text/html,application/xhtml+xml,*/*;q=0.8",
                headers=headers,
            ),
        )
        if self._logged_in:
            raise_terminal(response, 'ETAX_LEGACY', authenticated=True)
        return response

    # --- Mở trang nghiệp vụ (dùng chung cho tờ khai/GNT/thông báo) ---
    def _form_id_for_operation(self, html: str, operation: str, expected: str) -> str:
        """Trả form id/name thực tế của trang, chấp nhận cả khi cổng đổi id."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        if expected and (soup.find('form', id=expected) is not None
                         or soup.find('form', attrs={'name': expected}) is not None):
            return expected
        for form in soup.find_all("form"):
            fields = {
                str(field.get("name")): str(field.get("value") or "")
                for field in form.find_all("input")
                if field.get("name")
            }
            if fields.get("dse_operationName") != operation:
                continue
            identifier = form.get("id") or form.get("name")
            if identifier:
                return str(identifier)
        return ""

    def _transition_urls(self, html: str) -> list[str]:
        """URL chuyển tiếp mà trang legacy tự mở (JS hoặc meta refresh)."""
        candidates: list[str] = []
        for pattern in (
            r"(?:window|document|top|parent)\.location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
            r"location\.replace\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"<meta[^>]+http-equiv=['\"]refresh['\"][^>]+url=([^'\";\"]+)",
        ):
            candidates.extend(unescape(match.group(1)) for match in re.finditer(pattern, html, re.I))
        return [
            urljoin(f"{LEGACY_ETAX_BASE}/", value)
            for value in candidates
            if "dse_sessionId=" in value
        ]

    def _auto_submit_operation_form(self, response, operation: str):
        """Bấm nút mặc định của form ``dse_operationName=<operation>`` nếu cổng trả về."""
        soup = BeautifulSoup(response.text, "html.parser")
        for form in soup.find_all("form"):
            action, fields = _form_data(form)
            if fields.get("dse_operationName") != operation:
                continue
            if fields.get("dse_nextEventName") not in {"", "start"}:
                continue
            if "dse_sessionId" not in fields:
                continue
            return self._post_fields(action, fields, getattr(response, "url", "") or LEGACY_ETAX_BASE)
        return None

    def _settle_operation_page(self, response, operation: str, expected_form: str):
        """Đi qua tối đa hai bước chuyển tiếp cho tới khi thấy form nghiệp vụ."""
        for _ in range(3):
            raise_terminal(response, 'ETAX_LEGACY', authenticated=True)
            if response.status_code == 200 and self._form_id_for_operation(response.text, operation, expected_form):
                return response
            targets = self._transition_urls(response.text)
            target = next((url for url in targets if operation in url), targets[0] if targets else "")
            if target:
                response = self.http.get(
                    target,
                    headers=build_page_headers(
                        profile=self.profile,
                        headers={"Referer": getattr(response, "url", "") or LEGACY_ETAX_BASE},
                    ),
                )
                continue
            submitted = self._auto_submit_operation_form(response, operation)
            if submitted is not None:
                response = submitted
                continue
            break
        return response

    def _open_operation_page(self, operation: str, expected_form: str, label: str):
        """Mở trang nghiệp vụ legacy và trả ``(response, form_id)`` thực tế.

        Ưu tiên liên kết mà trang chủ đã phát cho phiên hiện tại (mang đúng
        ``dse_pageId``/``dse_processorState``), sau đó mới tự dựng URL như cũ.
        Cổng có lúc trả trang chuyển tiếp hoặc đổi id form, nên cả hai trường hợp
        đều được xử lý trước khi báo lỗi.
        """
        if not self.dse_session_id or not self.home_page_id:
            raise LegacyPageError("Chưa đăng nhập legacy")
        candidates: list[str] = []
        menu_url = _operation_url(self.home_page_html, operation)
        if menu_url:
            candidates.append(menu_url)
        candidates.append("")
        last = None
        for candidate in candidates:
            if candidate:
                response = self.http.get(
                    candidate,
                    headers=build_page_headers(profile=self.profile),
                )
            else:
                response = self.http.get(
                    f"{LEGACY_ETAX_BASE}/Request",
                    params={
                        "dse_sessionId": self.dse_session_id,
                        "dse_applicationId": "-1",
                        "dse_pageId": self.home_page_id,
                        "dse_operationName": operation,
                        "dse_processorState": "initial",
                        "dse_nextEventName": "start",
                    },
                    headers=build_page_headers(profile=self.profile),
                )
            response = self._settle_operation_page(response, operation, expected_form)
            last = response
            if response.status_code == 200:
                form_id = self._form_id_for_operation(response.text, operation, expected_form)
                if form_id:
                    return response, form_id
        status = getattr(last, "status_code", "?")
        detail = _page_detail(last) if last is not None else ""
        suffix = f": {detail}" if detail else ""
        self.logger.error("Không mở được trang %s legacy: HTTP=%s%s", label, status, suffix)
        raise LegacyPageError(
            f"Không mở được trang tra cứu {label} legacy (HTTP {status}){suffix}. "
            "Đã thử liên kết trên trang chủ và tự dựng lại URL theo phiên hiện tại; "
            "nếu vẫn lỗi, kiểm tra tài khoản có chức năng này trên trang Thuế điện tử "
            "hoặc xem nhật ký kỹ thuật."
        )

    # --- Giai đoạn 3: tra cứu ---
    def search(self, period: SearchPeriod, page: int) -> PageResult:
        from ..dates import format_date

        self.login()
        if not self._search_page_html:
            self._open_search_page()

        response = self._post_form(
            self._search_page_html, self._search_form_id, self._search_page_url,
            {
                "dse_operationName": "traCuuToKhaiProc",
                "dse_nextEventName": "query",
                "pn": page,
                "maTKhai": "00",
                "tenTKhai": "",
                "kieuKy": "",
                "ma_gd": "",
                "qryFromDate": format_date(period.start),
                "qryToDate": format_date(period.end),
            },
        )
        if response.status_code != 200:
            return PageResult(http_status=response.status_code)
        # Không thay form tốt bằng trang lỗi/hết phiên HTTP 200.
        empty_result = "Chưa có tờ khai nào" in response.text
        form_id = self._form_id_for_operation(response.text, 'traCuuToKhaiProc', self._search_form_id)
        if not form_id or (
            _RESULT_TABLE_ID not in response.text and not empty_result
        ):
            if self.session_state is not None:
                raise LegacyEtaxError(
                    "Cổng trả HTTP 200 nhưng thiếu bảng/form tờ khai. "
                    "Hãy thử lại; nếu vẫn lỗi, đăng xuất rồi đăng nhập hoặc xem nhật ký."
                )
            self.logger.warning("Legacy không trả bảng kết quả/form tra cứu; có thể đã hết phiên")
            return PageResult(http_status=response.status_code)
        self._search_form_id = form_id
        self._search_page_html = response.text
        self._search_page_url = response.url
        parsed = parse_record_table(response.text, self.source)
        return PageResult(records=parsed.records, total_pages=_total_pages(response.text),
                          http_status=response.status_code, diagnostics=parsed.diagnostics)

    def _open_search_page(self) -> None:
        """Mở trang tra cứu tờ khai (nơi có form ``traCuuKhaiForm``)."""
        response, form_id = self._open_operation_page(
            "traCuuToKhaiProc", _SEARCH_FORM_ID, "tờ khai"
        )
        self._search_form_id = form_id
        self._search_page_html = response.text
        self._search_page_url = response.url

    # --- Giai đoạn 4: tải ---
    def fetch_detail_csrf(self, record: CaseRecord) -> tuple[str, str]:
        """Trang legacy không dùng CSRF; trả URL tham chiếu cho ``download``."""
        return f"{LEGACY_ETAX_BASE}/Request?messageId={record.ma_ho_so}", ""

    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        """Tải XML tờ khai rồi gói vào ZIP trong bộ nhớ.

        Trang cũ trả XML qua ``downTkhai&messageId=...``; gói ZIP ngay tại đây
        (dạng JSON base64 giống cổng DVC) nên ``ZipStore`` và metadata dùng
        chung với hai nguồn còn lại.
        """
        _, fields = _form_fields(self._search_page_html, self._search_form_id)
        keep = ("dse_sessionId", "dse_applicationId", "dse_pageId", "dse_processorState", "dse_processorId")
        params = {key: fields[key] for key in keep if fields.get(key)}
        params.update(
            {
                "dse_operationName": "traCuuToKhaiProc",
                "dse_nextEventName": "downTkhai",
                "messageId": record.ma_ho_so,
            }
        )
        response = self.http.get(
            f"{LEGACY_ETAX_BASE}/Request",
            params=params,
            headers=build_xhr_headers(
                profile=self.profile,
                accept="*/*",
                headers={"Referer": self._search_page_url or LEGACY_ETAX_BASE},
            ),
        )
        if response.status_code != 200:
            return response
        content_type = response.headers.get("content-type", "").lower()
        from ..integrity import validate_xml
        xml_ok = validate_xml(response.content, "declaration").ok
        if "text/html" in content_type or not xml_ok:
            self.logger.error(
                "Legacy không trả XML hợp lệ cho %s (hết phiên hoặc tờ khai không tải được)",
                record.ma_ho_so,
            )
            return _HtmlInsteadOfFile(response)
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr(f'{safe_filename_part(record.ma_ho_so, 50)}.xml', response.content)
        return DownloadArtifact(buffer.getvalue(), 'zip', 'DECLARATION', record.key)


class _HtmlInsteadOfFile:
    """Phản hồi giả khi trang legacy trả HTML (lỗi) thay vì file."""

    def __init__(self, response) -> None:
        self.status_code = response.status_code
        self.text = response.text
        self.content = response.content
        self.headers = response.headers

    def json(self):
        raise ValueError("Legacy trả HTML thay vì file")


class EtaxLegacyFallback(Portal):
    """Bọc một portal gốc (DVC/ETAX) và định tuyến hồ sơ theo nguồn của nó.

    Pipeline tự quyết định khi nào cần hỏi trang cũ (đoạn ngày trước mốc mà
    portal gốc không tải được hồ sơ nào — cổng có lúc còn hiện hồ sơ cũ trong
    kết quả tra cứu nhưng máy chủ tải ZIP trả "Không tìm thấy hồ sơ tương ứng",
    đã gặp thật với tờ khai 2020) rồi gọi trực tiếp ``portal.legacy``.
    Lớp này chỉ đảm bảo mọi hồ sơ — bất kể nguồn — đều tải đúng chỗ khi đi qua
    một portal duy nhất trong ``pipeline._download``.
    """

    source = SOURCE_ETAX_LEGACY
    detail_loai = SOURCE_ETAX_LEGACY
    #: Trang legacy không dùng CSRF token khi tải.
    csrf_optional = True

    def __init__(self, primary: Portal, legacy: EtaxLegacyPortal, *, logger: logging.Logger | None = None) -> None:
        self.primary = primary
        self.legacy = legacy
        self.settings = primary.settings
        self.logger = logger or logging.getLogger("gdt_tax.portal.etax_legacy_fallback")

    def search(self, period: SearchPeriod, page: int) -> PageResult:
        return self.primary.search(period, page)

    def fetch_detail_csrf(self, record: CaseRecord) -> tuple[str, str]:
        if record.nguon == SOURCE_ETAX_LEGACY:
            return self.legacy.fetch_detail_csrf(record)
        return self.primary.fetch_detail_csrf(record)

    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        if record.nguon == SOURCE_ETAX_LEGACY:
            return self.legacy.download(record, detail_url, csrf)
        return self.primary.download(record, detail_url, csrf)


__all__ = ["EtaxLegacyFallback", "EtaxLegacyPortal"]
