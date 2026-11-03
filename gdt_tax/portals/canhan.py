"""Tài khoản cá nhân trên trang Thuế điện tử ``canhan.gdt.gov.vn``.

HAR ``thuedientu_canhan.har`` xác nhận đây là một phiên DSE riêng, **không**
dùng chung endpoint với doanh nghiệp hay DVC::

    EstablishSession → retailIndexProc → retailUserLoginProc
      → Mã số thuế + Mã kiểm tra → Mật khẩu
      → retailHomePageProc
      → retailSearchVoucherProc   (tờ khai)
      → retailSearchTaxNoticesProc (thông báo)

Tờ khai trả XML ``HSoThueDTu`` qua ``frmtcuu`` + ``dse_nextEventName=download``;
thông báo trả XML ``TBaoThueDTu`` hoặc PDF qua cùng cơ chế với ``idTBao`` /
``loaitbao``. Module này chỉ dùng các tham số đã thấy trong HAR, không suy đoán
endpoint của doanh nghiệp.
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
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from ..auth_outcomes import AuthFailure, AuthOutcome, classify_response, raise_terminal
from ..constants import CANHAN_BASE, CANHAN_ORIGIN, SOURCE_ETAX_LEGACY
from ..contracts import DownloadArtifact, Solver, Transport
from ..dates import format_date
from ..errors import LegacyEtaxError, LegacyPageError
from ..headers import build_image_headers, build_page_headers, build_xhr_headers
from ..integrity import validate_xml
from ..legacy_session import LegacySessionState
from ..models import CaseRecord, PageResult, SearchPeriod
from ..naming import safe_filename_part
from ..table_contracts import ParseDiagnostics
from ..tb.models import TbPageResult, ThongBao

CANHAN_REQUEST = f"{CANHAN_BASE}/Request"

_DECLARATION_OPERATION = "retailSearchVoucherProc"
_NOTICE_OPERATION = "retailSearchTaxNoticesProc"
_SEARCH_FORM = "frm"
_DETAIL_FORM = "frmtcuu"
_LOGIN_FORM = "loginForm"
_CONDUCT_FORM = "loginConductForm"
_CONCURRENT_LOGIN_MARKER = "đang đăng nhập hệ thống"
_SESSION_FIELDS = ("dse_sessionId", "dse_applicationId", "dse_pageId",
                   "dse_processorState", "dse_processorId", "dse_errorPage")


def _clean(value: str) -> str:
    return " ".join((value or "").split())


def _form_node(html: str, form_id: str):
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id=form_id) if form_id else None
    if form is None and form_id:
        form = soup.find("form", attrs={"name": form_id})
    return form


def _form_fields(html: str, form_id: str) -> tuple[str, dict[str, str]]:
    form = _form_node(html, form_id)
    if form is None:
        raise LegacyEtaxError(f"Không tìm thấy form {form_id!r} trên trang cá nhân")
    action = str(form.get("action") or "/ICanhan/Request")
    fields: dict[str, str] = {}
    for field in form.find_all("input"):
        name = field.get("name")
        # Trình duyệt không gửi nút khi form.submit() bằng JS; gửi kèm
        # ``button=Đồng ý`` làm cổng trả SystemError ở bước xác nhận.
        if name and str(field.get("type") or "").casefold() not in {
                "button", "submit", "reset", "image"}:
            fields[str(name)] = str(field.get("value") or "")
    return urljoin(f"{CANHAN_BASE}/", action), fields


def _form_id_for_operation(html: str, operation: str, expected: str = "") -> str:
    soup = BeautifulSoup(html, "html.parser")
    if expected:
        form = (soup.find("form", id=expected)
                or soup.find("form", attrs={"name": expected}))
        if form is not None:
            values = {str(field.get("name")): str(field.get("value") or "")
                      for field in form.find_all("input") if field.get("name")}
            # Trang cá nhân có nhiều form cùng trang; chỉ nhận form đúng
            # operation, tránh gửi ``goProcForm`` sang bước đăng nhập và nhận
            # trang SystemError.
            if not operation or values.get("dse_operationName") == operation:
                return expected
    for form in soup.find_all("form"):
        fields = {str(field.get("name")): str(field.get("value") or "")
                  for field in form.find_all("input") if field.get("name")}
        if fields.get("dse_operationName") != operation:
            continue
        identifier = form.get("id") or form.get("name")
        if identifier:
            return str(identifier)
    return ""


def _transition_url(html: str, operation: str = "") -> str:
    candidates: list[str] = []
    for pattern in (
        r"(?:window|document|top|parent)\.location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
        r"location\.replace\(\s*['\"]([^'\"]+)['\"]\s*\)",
        r"<meta[^>]+http-equiv=['\"]refresh['\"][^>]+url=([^'\";\"]+)",
    ):
        candidates.extend(unescape(match.group(1)) for match in re.finditer(pattern, html, re.I))
    for value in candidates:
        if "dse_sessionId=" in value and (not operation or operation in value):
            return urljoin(f"{CANHAN_BASE}/", value)
    for value in candidates:
        if "dse_sessionId=" in value:
            return urljoin(f"{CANHAN_BASE}/", value)
    return ""


def _operation_url(html: str, operation: str) -> str:
    decoded = unescape(html or "")
    pattern = r"(?:https?://[^\s'\"<>]+|/ICanhan/Request\?[^\s'\"<>]+)"
    for match in re.finditer(pattern, decoded):
        value = match.group(0)
        if f"dse_operationName={operation}" in value and "dse_sessionId=" in value:
            return urljoin(f"{CANHAN_BASE}/", value)
    return ""


def _query_parameter(url: str, name: str) -> str:
    values = parse_qs(urlparse(url).query).get(name)
    return values[0] if values else ""


def _page_count(html: str) -> int | None:
    text = " ".join(BeautifulSoup(html, "html.parser").stripped_strings)
    # Cổng cá nhân ghi "Trang 1 /Tổng số 3 trang."; giữ thêm dạng cũ "Trang 1/3".
    match = re.search(r"Tổng số\s*(\d+)\s*trang", text, re.I)
    if match is None:
        match = re.search(r"Trang\s*\d+\s*/\s*(\d+)", text, re.I)
    return int(match.group(1)) if match else None


def _page_url(html: str, page: int) -> str:
    """Lấy đúng href pager của trang ``page`` (đã unescape ``&amp;``)."""
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find(id="divPagination") or soup
    for anchor in container.find_all("a", href=True):
        if anchor.get_text(strip=True) == str(page):
            return urljoin(f"{CANHAN_BASE}/", unescape(str(anchor["href"])))
    return ""


def _total_pages(html: str) -> int | None:
    """Tổng số trang; không có pager và không có link trang 2 nghĩa là một trang."""
    pages = _page_count(html)
    if pages is None and not _page_url(html, 2):
        return 1
    return pages


def _transient_error(response) -> bool:
    """Cổng cá nhân trả HTTP 200 nhưng là trang SystemError/đang bận."""
    if getattr(response, "status_code", 0) != 200:
        return False
    content_type = (response.headers.get("content-type", "") or "").lower()
    text = getattr(response, "text", "") or ""
    return "text/html" in content_type and any(
        marker in text for marker in ("SystemError", "Hệ thống bận", "Xin vui lòng thử lại sau"))


def _has_operation_form(html: str, operation: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    return any(form.find("input", attrs={"name": "dse_operationName", "value": operation})
               is not None for form in soup.find_all("form"))


def is_empty_declaration_page(html: str) -> bool:
    """Trang tra cứu tờ khai hợp lệ nhưng không có bảng kết quả nào.

    Cổng cá nhân vẫn hiện form tra cứu và bảng giữ chỗ ``viewTableTraCuu``
    nhưng không render bảng ``confirm_table`` khi kỳ đã chọn không có hồ sơ.
    Đây là bằng chứng rỗng, không phải cổng đổi cấu trúc.
    """
    if not _has_operation_form(html, _DECLARATION_OPERATION):
        return False
    if _table_with_headers(html, "Mã giao dịch", "Ngày nộp")[0]:
        return False
    return BeautifulSoup(html, "html.parser").find(id="viewTableTraCuu") is not None


def is_empty_notice_page(html: str) -> bool:
    """Trang tra cứu thông báo hợp lệ nhưng không có bảng kết quả."""
    if not _has_operation_form(html, _NOTICE_OPERATION):
        return False
    if _table_with_headers(html, "Số thông báo", "Ngày gửi")[0]:
        return False
    return BeautifulSoup(html, "html.parser").find(id="viewTableTraCuu") is not None


def _header_index(headers: list[str], *needles: str) -> int:
    for index, header in enumerate(headers):
        normalized = header.casefold()
        if all(needle.casefold() in normalized for needle in needles):
            return index
    return -1


def _table_with_headers(html: str, *needles: str) -> tuple[list[str], list[Tag]]:
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [_clean(cell.get_text(" ", strip=True))
                   for cell in rows[0].find_all(["td", "th"], recursive=False)]
        if all(any(needle.casefold() in header.casefold() for header in headers)
               for needle in needles):
            return headers, rows[1:]
    return [], []


def parse_declarations(html: str) -> list[CaseRecord]:
    """Đọc bảng ``confirm_table`` của màn hình tra cứu tờ khai cá nhân."""
    headers, rows = _table_with_headers(html, "Mã giao dịch", "Ngày nộp")
    if not headers:
        return []
    columns = {
        "transaction": _header_index(headers, "mã giao dịch"),
        "title": _header_index(headers, "tờ khai"),
        "period": _header_index(headers, "kỳ tính thuế"),
        "kind": _header_index(headers, "loại tờ khai"),
        "submission": _header_index(headers, "lần nộp"),
        "attachment": _header_index(headers, "gửi phụ lục"),
        "sent": _header_index(headers, "ngày nộp"),
        "office": _header_index(headers, "nơi nộp"),
        "status": _header_index(headers, "trạng thái"),
    }
    if columns["status"] < 0:
        for index, header in enumerate(headers):
            if "tiến trình" in header.casefold():
                columns["status"] = index
                break
    records: list[CaseRecord] = []
    for row in rows:
        cells = [_clean(cell.get_text(" ", strip=True))
                 for cell in row.find_all("td", recursive=False)]
        if len(cells) < 4:
            continue
        match = (re.search(r"viewTKhai\(\s*['\"]([^'\"]+)['\"]", str(row))
                 or re.search(r"downloadGNT\(\s*['\"]?(\d+)['\"]?", str(row)))
        transaction = match.group(1) if match else (cells[columns["transaction"]]
                                                     if columns["transaction"] >= 0 else "")
        if not transaction:
            continue

        def value(name: str, cells: list[str] = cells) -> str:
            index = columns[name]
            return cells[index] if 0 <= index < len(cells) else ""

        records.append(CaseRecord(
            ma_ho_so=transaction,
            nguon=SOURCE_ETAX_LEGACY,
            to_khai=value("title"),
            ky_tinh_thue=value("period"),
            loai_to_khai=value("kind"),
            lan_nop=value("submission"),
            lan_bo_sung=value("attachment"),
            ngay_nop=value("sent"),
            noi_nop=value("office"),
            trang_thai=value("status"),
        ))
    return records


def parse_notices(html: str) -> list[ThongBao]:
    """Đọc bảng thông báo; lấy ``idTBao``/``loaitbao`` từ link tải của từng hàng."""
    headers, rows = _table_with_headers(html, "Số thông báo", "Ngày gửi")
    if not headers:
        return []
    columns = {
        "number": _header_index(headers, "số thông báo"),
        # "Số thông báo" cũng chứa chữ "thông báo"; chọn đúng cột tiêu đề.
        "title": next((index for index, header in enumerate(headers)
                       if header.casefold() == "thông báo"), -1),
        "sent": _header_index(headers, "ngày gửi"),
        "transaction": _header_index(headers, "mã giao dịch"),
    }
    notices: list[ThongBao] = []
    for row in rows:
        cells = [_clean(cell.get_text(" ", strip=True))
                 for cell in row.find_all("td", recursive=False)]
        if len(cells) < 3:
            continue
        match = re.search(
            r"downloadGNT\(\s*['\"]?(\d+)['\"]?\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
            str(row),
        )
        if not match:
            continue

        def value(name: str, cells: list[str] = cells) -> str:
            index = columns[name]
            return cells[index] if 0 <= index < len(cells) else ""

        number = value("number")
        notices.append(ThongBao(
            message_id=match.group(1),
            ma_tbao=match.group(2),
            ma_thong_bao=match.group(1),
            ten_thong_bao=value("title"),
            so_thong_bao=number,
            ngay_gui=value("sent"),
            trang_thai="",
        ))
    return notices


class CanhanPortal:
    """Phiên DSE cá nhân: đăng nhập, tờ khai và thông báo."""

    source = SOURCE_ETAX_LEGACY
    detail_loai = SOURCE_ETAX_LEGACY
    csrf_optional = True

    def __init__(self, http: Transport, captcha: Solver, settings,
                 logger: logging.Logger | None = None, *,
                 session_state: LegacySessionState | None = None) -> None:
        self.http, self.captcha, self.settings = http, captcha, settings
        self.logger = logger or logging.getLogger("gdt_tax.portal.canhan")
        self.session_state = session_state
        self.dse_session_id = ""
        self.home_page_id = ""
        self.home_page_html = ""
        self._logged_in = False
        self._search_page_html = ""
        self._search_page_url = ""
        self._search_form_id = _SEARCH_FORM
        self._notice_page_html = ""
        self._notice_page_url = ""
        self._notice_form_id = _SEARCH_FORM
        self.last_download_error = ""

    @property
    def profile(self):
        return self.settings.header_profile

    @property
    def request_url(self) -> str:
        return CANHAN_REQUEST

    # --- Đăng nhập ---
    def login(self) -> None:
        if self.session_state is not None and self.session_state.authenticated:
            self.dse_session_id = self.session_state.dse_session_id
            self.home_page_id = self.session_state.home_page_id
            self.home_page_html = self.session_state.home_page_html
            self._logged_in = True
            return
        if self._logged_in:
            return

        page = self._start_session()
        page = self._reach_login_options(page)
        self._submit_login(page)
        self._logged_in = True
        if self.session_state is not None:
            self.session_state.dse_session_id = self.dse_session_id
            self.session_state.home_page_id = self.home_page_id
            self.session_state.home_page_html = self.home_page_html
            self.session_state.authenticated = True
        self.logger.info("ĐĂNG NHẬP THUẾ ĐIỆN TỬ CÁ NHÂN THÀNH CÔNG")

    def _start_session(self):
        # Vào đúng cửa ngõ như trình duyệt: /ICanhan/ tự chuyển tới
        # retailJumpProc/EstablishSession, rồi ``mainForm`` mở retailIndexProc.
        # Gọi thẳng EstablishSession với operation khác sẽ nhận SystemError.
        response = self.http.get(
            f"{CANHAN_BASE}/",
            headers=build_page_headers(profile=self.profile, site="none"),
        )
        raise_terminal(response, "ETAX_LEGACY")
        for _ in range(4):
            self.dse_session_id = (_query_parameter(getattr(response, "url", ""), "dse_sessionId")
                                   or self.dse_session_id)
            target = _transition_url(response.text)
            if target:
                response = self.http.get(target, headers=build_page_headers(profile=self.profile))
                continue
            main_form = _form_node(response.text, "mainForm")
            if main_form is not None:
                action, fields = _form_fields(response.text, "mainForm")
                response = self.http.post(
                    action, data=fields, headers=build_page_headers(profile=self.profile))
                continue
            break
        if not self.dse_session_id:
            self.dse_session_id = self._field_from_html(response.text, "dse_sessionId")
        if not self.dse_session_id:
            raise LegacyEtaxError("Không lấy được dse_sessionId của trang cá nhân")
        return response

    def _post_operation(self, page, operation: str, event: str):
        form_id = _form_id_for_operation(page.text, operation, "goProcForm") or "goProcForm"
        if _form_node(page.text, form_id) is None:
            target = _operation_url(page.text, operation)
            if target:
                return self.http.get(target, headers=build_page_headers(profile=self.profile))
            return page
        return self._post_form(
            page.text, form_id, getattr(page, "url", CANHAN_REQUEST),
            {"dse_operationName": operation, "dse_nextEventName": event},
        )

    def _reach_login_options(self, page):
        if _form_node(page.text, _LOGIN_FORM) is None:
            form_id = _form_id_for_operation(page.text, "retailUserLoginProc")
            if not form_id:
                page = self._post_operation(page, "retailUserLoginProc", "start")
                form_id = _form_id_for_operation(page.text, "retailUserLoginProc")
            if form_id:
                page = self._post_form(
                    page.text, form_id, getattr(page, "url", CANHAN_REQUEST),
                    {"dse_operationName": "retailUserLoginProc", "dse_nextEventName": "ok"},
                )
        return page

    def _submit_login(self, page) -> None:
        last_message = "không rõ"
        for attempt in range(1, max(1, int(self.settings.login_attempts)) + 1):
            if _form_node(page.text, _LOGIN_FORM) is None:
                raise AuthFailure(AuthOutcome.SCHEMA_UNKNOWN)
            image = self._captcha_image(getattr(page, "url", CANHAN_REQUEST))
            code = self.captcha.solve(image) if image else ""
            if not code:
                last_message = "không đọc được mã kiểm tra"
                self.logger.warning("Cá nhân: %s (lần %s)", last_message, attempt)
                continue
            response = self._post_form(
                page.text, _LOGIN_FORM, getattr(page, "url", CANHAN_REQUEST),
                {"_userName": self.settings.username, "capcha": code,
                 "dse_nextEventName": "ok"},
                navigation=True,
            )
            password_form = _form_node(response.text, _LOGIN_FORM)
            if password_form is None or not any(
                    field.get("name") == "_password" for field in password_form.find_all("input")):
                rejected = getattr(self.captcha, "rejected", None)
                if callable(rejected):
                    rejected()
                last_message = "mã kiểm tra không đúng"
                self.logger.warning("Cá nhân: %s (lần %s)", last_message, attempt)
                page = response
                continue
            final = self._post_form(
                response.text, _LOGIN_FORM, getattr(response, "url", CANHAN_REQUEST),
                {"_password": self.settings.password, "dse_nextEventName": "ok"},
                navigation=True,
            )
            # Cổng chặn khi tài khoản còn phiên ở máy/trình duyệt khác và hỏi
            # "Chọn Đồng ý để đăng nhập". Đây không phải sai mật khẩu.
            final = self._confirm_concurrent_login(final)
            if not self._login_succeeded(final):
                if _CONDUCT_FORM in (getattr(final, "text", "") or ""):
                    raise LegacyEtaxError(
                        "Tài khoản vẫn đang được đăng nhập ở nơi khác và cổng chưa "
                        "chấp nhận phiên này. Hãy đăng xuất phiên kia rồi thử lại."
                    )
                raise AuthFailure(AuthOutcome.INVALID_CREDENTIALS)
            accepted = getattr(self.captcha, "accepted", None)
            if callable(accepted):
                accepted()
            self._open_home_page(final)
            return
        raise AuthFailure(AuthOutcome.CAPTCHA_INVALID if "mã kiểm tra" in last_message
                          else AuthOutcome.SCHEMA_UNKNOWN)

    def _download_post(self, html: str, form_id: str, referer: str, data: Mapping[str, Any],
                       *, attempts: int = 3):
        """Tải tệp, thử lại khi cổng trả trang SystemError tạm thời."""
        last = None
        for attempt in range(1, attempts + 1):
            last = self._post_form(html, form_id, referer, data)
            if not _transient_error(last):
                return last
            if attempt < attempts:
                self.logger.warning(
                    "Cổng báo SystemError khi tải tệp; thử lại lần %s/%s", attempt + 1, attempts)
                time.sleep(1.5 * attempt)
        return last

    def _confirm_concurrent_login(self, page):
        """Bấm ``Đồng ý`` khi cổng cảnh báo tài khoản đang đăng nhập ở phiên khác."""
        text = getattr(page, "text", "") or ""
        if _CONDUCT_FORM not in text or _CONCURRENT_LOGIN_MARKER not in text.casefold():
            return page
        self.logger.info(
            "Cổng báo tài khoản đang đăng nhập ở phiên khác; xác nhận tiếp tục phiên này"
        )
        return self._post_form(
            text, _CONDUCT_FORM, getattr(page, "url", CANHAN_REQUEST),
            {"_loginedConduct": "forceLastLogin", "dse_nextEventName": "ok"},
            navigation=True,
        )

    def _login_succeeded(self, response) -> bool:
        if getattr(response, "status_code", 0) != 200:
            return False
        if classify_response(response, "ETAX_LEGACY") in {
                AuthOutcome.INVALID_CREDENTIALS, AuthOutcome.EXPIRED_SESSION}:
            return False
        text = getattr(response, "text", "") or ""
        if any(marker in text for marker in ("Tên đăng nhập hoặc mật khẩu không đúng",
                                             "Mật khẩu không đúng", "Tài khoản đã bị khóa")):
            return False
        form = _form_node(text, _LOGIN_FORM)
        has_password = form is not None and any(
            field.get("name") == "_password" for field in form.find_all("input"))
        return not has_password and ("retailHomePageProc" in text or "Đăng xuất" in text
                                     or "Quản lý thuế" in text)

    def _open_home_page(self, login_result) -> None:
        page = self._post_operation(login_result, "retailHomePageProc", "start")
        self.home_page_html = getattr(page, "text", "") or getattr(login_result, "text", "")
        self.home_page_id = (_query_parameter(getattr(page, "url", ""), "dse_pageId")
                             or self._field_from_html(self.home_page_html, "dse_pageId"))
        if not self.home_page_id:
            raise LegacyEtaxError("Không lấy được dse_pageId của trang chủ cá nhân")

    def _field_from_html(self, html: str, name: str) -> str:
        soup = BeautifulSoup(html or "", "html.parser")
        field = soup.find("input", attrs={"name": name})
        return str(field.get("value") or "") if field else ""

    def _captcha_image(self, referer: str) -> bytes | None:
        response = self.http.get(
            f"{CANHAN_BASE}/servlet/ImageServlet",
            params={"d": int(time.time() * 1000)},
            headers=build_image_headers(profile=self.profile, headers={"Referer": referer}),
        )
        content_type = response.headers.get("content-type", "").lower()
        if response.status_code == 200 and "image" in content_type and len(response.content) > 100:
            return response.content
        self.logger.error("CAPTCHA cá nhân lỗi: HTTP=%s content-type=%s",
                          response.status_code, content_type or "?")
        return None

    def _post_form(self, html: str, form_id: str, referer: str,
                   overrides: Mapping[str, Any], *, navigation: bool = False):
        action, fields = _form_fields(html, form_id)
        fields.update({key: str(value) for key, value in overrides.items()})
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": CANHAN_ORIGIN,
            "Referer": referer,
        }
        if navigation:
            response = self.http.post(action, data=fields, headers=build_page_headers(
                profile=self.profile, headers=headers))
        else:
            response = self.http.post(action, data=fields, headers=build_xhr_headers(
                profile=self.profile,
                accept="text/html,application/xhtml+xml,*/*;q=0.8",
                headers={**headers, "X-Requested-With": "XMLHttpRequest"},
            ))
        if self._logged_in:
            raise_terminal(response, "ETAX_LEGACY", authenticated=True)
        return response

    # --- Mở trang nghiệp vụ ---
    def _open_operation(self, operation: str, form_id: str, label: str):
        if not self.dse_session_id or not self.home_page_id:
            raise LegacyPageError("Chưa đăng nhập trang Thuế điện tử cá nhân")
        candidates = []
        menu_url = _operation_url(self.home_page_html, operation)
        if menu_url:
            candidates.append(menu_url)
        candidates.append("")
        last = None
        for candidate in candidates:
            if candidate:
                page = self.http.get(candidate, headers=build_page_headers(profile=self.profile))
            else:
                page = self.http.get(
                    CANHAN_REQUEST,
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
            page = self._settle(page, operation, form_id)
            last = page
            real_form = _form_id_for_operation(page.text, operation, form_id)
            if page.status_code == 200 and real_form:
                return page, real_form
        status = getattr(last, "status_code", "?")
        raise LegacyPageError(
            f"Không mở được trang {label} của tài khoản cá nhân (HTTP {status}). "
            "Kiểm tra tài khoản có chức năng này trên trang Thuế điện tử cá nhân "
            "hoặc xem nhật ký kỹ thuật."
        )

    def _settle(self, page, operation: str, form_id: str):
        for _ in range(4):
            raise_terminal(page, "ETAX_LEGACY", authenticated=True)
            if page.status_code != 200:
                return page
            if _form_id_for_operation(page.text, operation, form_id):
                return page
            target = _transition_url(page.text, operation)
            if target:
                page = self.http.get(target, headers=build_page_headers(profile=self.profile))
                continue
            auto = self._auto_submit(page, operation)
            if auto is not None:
                page = auto
                continue
            break
        return page

    def _auto_submit(self, page, operation: str):
        soup = BeautifulSoup(page.text, "html.parser")
        for form in soup.find_all("form"):
            fields = {str(field.get("name")): str(field.get("value") or "")
                      for field in form.find_all("input") if field.get("name")}
            if fields.get("dse_operationName") != operation:
                continue
            if fields.get("dse_nextEventName") not in {"", "start"}:
                continue
            if "dse_sessionId" not in fields:
                continue
            action = urljoin(f"{CANHAN_BASE}/", str(form.get("action") or "/ICanhan/Request"))
            return self.http.post(action, data=fields, headers=build_page_headers(
                profile=self.profile))
        return None

    # --- Tờ khai ---
    def search(self, period: SearchPeriod, page: int) -> PageResult:
        self.login()
        if not self._search_page_html:
            opened, self._search_form_id = self._open_operation(
                _DECLARATION_OPERATION, _SEARCH_FORM, "tờ khai")
            self._search_page_html = opened.text
            self._search_page_url = getattr(opened, "url", CANHAN_REQUEST)
        response = self._query_declarations(period, page)
        if response.status_code != 200:
            return PageResult(http_status=response.status_code)
        empty = any(marker in response.text for marker in ("Chưa có tờ khai", "Không có dữ liệu"))
        empty_page = is_empty_declaration_page(response.text)
        form_id = _form_id_for_operation(response.text, _DECLARATION_OPERATION, self._search_form_id)
        if not form_id or ("Mã giao dịch" not in response.text and not empty and not empty_page):
            if self.session_state is not None:
                raise LegacyEtaxError(
                    "Cổng cá nhân trả HTTP 200 nhưng thiếu bảng/form tờ khai. "
                    "Hãy thử lại; nếu vẫn lỗi, đăng xuất rồi đăng nhập hoặc xem nhật ký."
                )
            return PageResult(http_status=response.status_code,
                              diagnostics=ParseDiagnostics(reasons=["RESULT_FORM_OR_TABLE_MISSING"]))
        self._search_form_id = form_id
        self._search_page_html = response.text
        self._search_page_url = getattr(response, "url", CANHAN_REQUEST)
        records = parse_declarations(response.text)
        if not records and empty_page:
            return PageResult(records=[], total_pages=None, http_status=response.status_code,
                              diagnostics=ParseDiagnostics(
                                  status="EMPTY_CONFIRMED", reasons=["PORTAL_EMPTY_RESULT"]))
        return PageResult(records=records, total_pages=_total_pages(response.text),
                          http_status=response.status_code)

    def _query_declarations(self, period: SearchPeriod, page: int):
        if page > 1:
            target = _page_url(self._search_page_html, page)
            if target:
                return self.http.get(target, headers=build_page_headers(profile=self.profile))
        if page <= 1:
            return self._post_form(
                self._search_page_html, self._search_form_id, self._search_page_url,
                {
                    "dse_operationName": _DECLARATION_OPERATION,
                    "dse_nextEventName": "ok",
                    "maGDichArr": ";;;;;;;;;",
                    "maGDich": "",
                    "cboTenTKhai": "",
                    "maHdong": "",
                    "_ngaygui": format_date(period.start),
                    "_denngay": format_date(period.end),
                },
            )
        return self.http.get(
            CANHAN_REQUEST,
            params={
                **self._session_fields(),
                "dse_operationName": _DECLARATION_OPERATION,
                "dse_errorPage": "error_page.jsp",
                "dse_nextEventName": "nextPage",
                "pn": str(page),
            },
            headers=build_page_headers(profile=self.profile),
        )

    def _session_fields(self) -> dict[str, str]:
        _, fields = _form_fields(self._search_page_html, self._search_form_id)
        return {key: fields[key] for key in _SESSION_FIELDS if fields.get(key)}

    def fetch_detail_csrf(self, record: CaseRecord) -> tuple[str, str]:
        return CANHAN_REQUEST, ""

    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        if not self._search_page_html:
            raise LegacyEtaxError("Chưa có trang kết quả tờ khai để tải theo")
        response = self._download_post(
            self._search_page_html, _DETAIL_FORM, self._search_page_url,
            {
                "dse_operationName": _DECLARATION_OPERATION,
                "dse_nextEventName": "download",
                "idTBao": record.ma_ho_so,
                "fileFormat": "9",
                "chkTTS": "1",
                "idBKe": "",
                "kyKK": "",
                "idTK": "",
                "maTKhai": "",
                "tenTKhai": "",
            },
        )
        if response.status_code != 200:
            return response
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type or not validate_xml(response.content, "declaration").ok:
            self.logger.error("Cá nhân không trả XML hợp lệ cho %s", record.ma_ho_so)
            return response
        # Cổng cá nhân trả XML trực tiếp; gói trong ZIP để dùng chung kho,
        # kiểm tra toàn vẹn và quy ước tên tệp với hai nguồn còn lại.
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{safe_filename_part(record.ma_ho_so, 50)}.xml", response.content)
        return DownloadArtifact(buffer.getvalue(), "zip", "DECLARATION", record.key)

    # --- Thông báo ---
    def search_tb(self, period: SearchPeriod, page: int) -> TbPageResult:
        self.login()
        if not self._notice_page_html:
            opened, self._notice_form_id = self._open_operation(
                _NOTICE_OPERATION, _SEARCH_FORM, "thông báo")
            self._notice_page_html = opened.text
            self._notice_page_url = getattr(opened, "url", CANHAN_REQUEST)
        response = self._query_notices(period, page)
        if response.status_code != 200:
            return TbPageResult(http_status=response.status_code)
        empty = any(marker in response.text for marker in
                    ("Không tìm thấy thông báo", "không có thông báo", "Chưa có thông báo",
                     "Không có dữ liệu"))
        empty_page = is_empty_notice_page(response.text)
        form_id = _form_id_for_operation(response.text, _NOTICE_OPERATION, self._notice_form_id)
        if not form_id or ("Số thông báo" not in response.text and not empty and not empty_page):
            if self.session_state is not None:
                raise_terminal(response, "ETAX_LEGACY", phase="page", authenticated=True)
                raise LegacyEtaxError(
                    "Cổng cá nhân trả HTTP 200 nhưng thiếu bảng/form thông báo. "
                    "Dữ liệu đã tải trước đó vẫn được giữ. Hãy thử lại hoặc đăng nhập lại."
                )
            return TbPageResult(http_status=response.status_code,
                                diagnostics=ParseDiagnostics(reasons=["RESULT_FORM_OR_TABLE_MISSING"]))
        self._notice_form_id = form_id
        self._notice_page_html = response.text
        self._notice_page_url = getattr(response, "url", CANHAN_REQUEST)
        records = parse_notices(response.text)
        if not records and empty_page:
            return TbPageResult(records=[], total_pages=None,
                                http_status=response.status_code,
                                diagnostics=ParseDiagnostics(
                                    status="EMPTY_CONFIRMED", reasons=["PORTAL_EMPTY_RESULT"]))
        return TbPageResult(records=records,
                            total_pages=_total_pages(response.text),
                            http_status=response.status_code)

    def _query_notices(self, period: SearchPeriod, page: int):
        if page > 1:
            target = _page_url(self._notice_page_html, page)
            if target:
                return self.http.get(target, headers=build_page_headers(profile=self.profile))
        if page <= 1:
            return self._post_form(
                self._notice_page_html, self._notice_form_id, self._notice_page_url,
                {
                    "dse_operationName": _NOTICE_OPERATION,
                    "dse_nextEventName": "ok",
                    "maGDichArr": ";;;;;;;;;",
                    "idHso": "",
                    "cboThongBao": "",
                    "_ngaygui": format_date(period.start),
                    "_denngay": format_date(period.end),
                },
            )
        _, fields = _form_fields(self._notice_page_html, self._notice_form_id)
        params = {key: fields[key] for key in _SESSION_FIELDS if fields.get(key)}
        params.update({
            "dse_operationName": _NOTICE_OPERATION,
            "dse_errorPage": "error_page.jsp",
            "dse_nextEventName": "nextPage",
            "pn": str(page),
        })
        return self.http.get(CANHAN_REQUEST, params=params,
                             headers=build_page_headers(profile=self.profile))

    def download_tb(self, record: ThongBao) -> bytes | None:
        self.last_download_error = ""
        if not self._notice_page_html:
            raise LegacyEtaxError("Chưa có trang kết quả thông báo để tải theo")
        response = self._download_post(
            self._notice_page_html, _DETAIL_FORM, self._notice_page_url,
            {
                "dse_operationName": _NOTICE_OPERATION,
                "dse_nextEventName": "download",
                "idTBao": record.message_id,
                "loaitbao": record.ma_tbao,
            },
        )
        if response.status_code != 200:
            self.last_download_error = (
                f"Cổng trả HTTP {response.status_code} khi tải thông báo; "
                "kiểm tra kết nối hoặc phiên đăng nhập.")
            return None
        if _transient_error(response):
            self.last_download_error = (
                "Cổng thuế tạm bận (SystemError) khi tải tệp sau 3 lần thử. "
                "Tệp chưa được lưu; hãy thử lại sau.")
            self.logger.error("Thông báo cá nhân %s: cổng tạm bận", record.message_id)
            return None
        content_type = response.headers.get("content-type", "").lower()
        is_pdf = response.content.startswith(b"%PDF-")
        is_xml = validate_xml(response.content, "notice").ok
        if "text/html" in content_type or not (is_pdf or is_xml):
            self.last_download_error = (
                "Cổng trả HTML hoặc dữ liệu không phải XML/PDF hoàn chỉnh; "
                "có thể phiên hết hạn hoặc cổng đổi định dạng.")
            self.logger.error("Thông báo cá nhân %s không tải được tệp", record.message_id)
            return None
        return response.content


__all__ = ["CANHAN_BASE", "CANHAN_REQUEST", "CanhanPortal", "is_empty_declaration_page",
           "is_empty_notice_page", "parse_declarations", "parse_notices"]
