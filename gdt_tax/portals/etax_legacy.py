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

import base64
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

from ..constants import LEGACY_ETAX_BASE, SOURCE_ETAX_LEGACY
from ..errors import LegacyEtaxError
from ..headers import build_image_headers, build_page_headers, build_xhr_headers
from ..http import HttpClient
from ..models import CaseRecord, PageResult, SearchPeriod
from ..parsing import parse_records
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


def _form_fields(html: str, form_id: str) -> tuple[str, dict[str, str]]:
    """Action URL và toàn bộ ô input có tên của một form trong trang legacy."""
    form = BeautifulSoup(html, "html.parser").find("form", id=form_id)
    if form is None:
        raise LegacyEtaxError(f"Không tìm thấy form id={form_id!r} trên trang legacy")
    action = str(form.get("action") or "/etaxnnt/Request")
    data: dict[str, str] = {}
    for field in form.find_all("input"):
        name = field.get("name")
        if name:
            data[str(name)] = str(field.get("value") or "")
    return urljoin(f"{LEGACY_ETAX_BASE}/", action), data


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
    ) -> None:
        super().__init__(http, captcha, settings, logger)
        self.login_attempts = (
            login_attempts if login_attempts is not None else settings.login_attempts
        )
        self.dse_session_id = ""
        self.home_page_id = ""
        self._search_page_html = ""
        self._search_page_url = ""
        self._logged_in = False

    # --- Đăng nhập trang cũ ---
    def login(self) -> None:
        """Đăng nhập trang Thuế điện tử cũ; thành công thì mới tra cứu được."""
        if self._logged_in:
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
        if response.status_code != 200 or _LOGIN_FORM_ID not in response.text:
            raise LegacyEtaxError("Trang legacy không trả về form đăng nhập")

        ok_response = self._submit_login(response)
        self._open_home_page(ok_response)
        self._logged_in = True
        self.logger.info("ĐĂNG NHẬP legacy THÀNH CÔNG (dse_sessionId=%s...)", self.dse_session_id[:6])

    def _submit_login(self, login_page):
        """Gửi tên đăng nhập/mật khẩu/CAPTCHA, thử lại khi đọc sai mã."""
        last_message = "không rõ"
        for attempt in range(1, self.login_attempts + 1):
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
            for message in _alerts(response.text):
                self.logger.info("Legacy: %s", message)
            if _LOGIN_OK_MARKER in response.text and _LOGIN_FORM_ID not in response.text:
                return response
            last_message = "tên đăng nhập/mật khẩu/CAPTCHA không được chấp nhận"
            self.logger.warning("Legacy: đăng nhập chưa được (lần %s/%s)", attempt, self.login_attempts)
        raise LegacyEtaxError(f"Không đăng nhập được trang legacy: {last_message}")

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
        self.http.get(home_url, headers=build_page_headers(profile=self.profile))
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
        return self.http.post(
            action,
            data=fields,
            headers=build_xhr_headers(
                profile=self.profile,
                accept="text/html,application/xhtml+xml,*/*;q=0.8",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": LEGACY_ETAX_BASE,
                    "Referer": referer,
                },
            ),
        )

    # --- Giai đoạn 3: tra cứu ---
    def search(self, period: SearchPeriod, page: int) -> PageResult:
        from ..dates import format_date

        self.login()
        if not self._search_page_html:
            self._open_search_page()

        response = self._post_form(
            self._search_page_html, _SEARCH_FORM_ID, self._search_page_url,
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
        self._search_page_html = response.text
        self._search_page_url = response.url
        records = parse_records(response.text, self.source)
        return PageResult(records=records, total_pages=_total_pages(response.text) or None,
                          http_status=response.status_code)

    def _open_search_page(self) -> None:
        """Mở trang tra cứu tờ khai (nơi có form ``traCuuKhaiForm``)."""
        if not self.dse_session_id or not self.home_page_id:
            raise LegacyEtaxError("Chưa đăng nhập legacy")
        response = self.http.get(
            f"{LEGACY_ETAX_BASE}/Request",
            params={
                "dse_sessionId": self.dse_session_id,
                "dse_applicationId": "-1",
                "dse_pageId": self.home_page_id,
                "dse_operationName": "traCuuToKhaiProc",
                "dse_processorState": "initial",
                "dse_nextEventName": "start",
            },
            headers=build_page_headers(profile=self.profile),
        )
        if response.status_code != 200 or _SEARCH_FORM_ID not in response.text:
            raise LegacyEtaxError("Không mở được trang tra cứu tờ khai legacy")
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
        _, fields = _form_fields(self._search_page_html, _SEARCH_FORM_ID)
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
        if "text/html" in content_type:
            self.logger.error(
                "Legacy trả HTML thay vì XML cho %s (hết phiên hoặc tờ khai không tải được)",
                record.ma_ho_so,
            )
            return _HtmlInsteadOfFile(response)
        return _XmlZipResponse(record, response.content)


class _HtmlInsteadOfFile:
    """Phản hồi giả khi trang legacy trả HTML (lỗi) thay vì file."""

    def __init__(self, response) -> None:
        self.status_code = response.status_code
        self.text = response.text
        self.content = response.content
        self.headers = response.headers

    def json(self):
        raise ValueError("Legacy trả HTML thay vì file")


class _XmlZipResponse:
    """ZIP chứa XML tờ khai, bọc dạng JSON base64 giống hình dạng cổng DVC trả.

    ``decode_zip_bytes`` thử ``response.json()`` trước rồi mới kiểm tra chữ ký
    ``PK``, nên trả JSON ``{"content": <base64>, "fileName": ...}`` là phần lưu
    dùng chung được mà không cần sửa ``storage``.
    """

    def __init__(self, record: CaseRecord, xml: bytes) -> None:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(f"{record.ma_ho_so}.xml", xml)
        self.status_code = 200
        self.headers = {"content-type": "application/json"}
        self._payload = {
            "content": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "fileName": f"{record.ma_ho_so}.zip",
        }
        self.content = buffer.getvalue()
        self.text = ""

    def json(self) -> dict[str, str]:
        return dict(self._payload)


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
