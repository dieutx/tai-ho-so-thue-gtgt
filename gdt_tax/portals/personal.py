"""Hai nguồn riêng của tài khoản cá nhân.

Tài khoản cá nhân dùng chung phiên đăng nhập Dịch vụ công với tài khoản doanh
nghiệp, nhưng dữ liệu nằm ở hai nơi khác nhau:

* **Tờ khai** — ``/tthc/ho-so/search`` với ``scope_tdt1=SELF``; tải ZIP qua
  ``/tths/validateIdTkhai`` + ``/tths/downloadhoso`` (giống DVC doanh nghiệp).
* **Thông báo của cơ quan thuế** — cổng ``canhan.gdt.gov.vn``; vào bằng SSO
  ``/tthc/sso/redirect-to-service?module=10607``, tra cứu bằng
  ``retailSearchTaxNoticesProc`` và tải PDF theo ``idTBao``.

Portal cá nhân không tự đăng nhập mật khẩu: pipeline đăng nhập một lần với
``doiTuong=CN`` rồi mới tạo portal, nên cả hai nguồn dùng chung cookie/CSRF.
"""

from __future__ import annotations

import base64
import logging
import re
import zipfile
from collections.abc import Mapping
from html import unescape
from io import BytesIO
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..constants import (
    CANHAN_BASE,
    CANHAN_ORIGIN,
    CANHAN_REQUEST,
    DVC_SSO_CANHAN_MODULE,
    DVC_SSO_REDIRECT,
    ORIGIN,
    SOURCE_CANHAN,
    SOURCE_DVC_PERSONAL,
)
from ..dates import format_date
from ..errors import LoginError
from ..headers import build_page_headers
from ..http import HttpClient
from ..models import CaseRecord, PageResult, SearchPeriod
from ..naming import safe_filename_part
from ..parsing import page_count, parse_records
from .base import Portal
from .dvc import DvcPortal

#: Tham số tìm kiếm cố định mà form thông báo gửi lên cổng cá nhân.
_SEARCH_STATE = "searchTaxJsp"
_SEARCH_OPERATION = "retailSearchTaxNoticesProc"
_EMPTY_TRANSACTION_IDS = ";;;;;;;;;"
_JS_REDIRECT_RE = re.compile(r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", re.I)
_ATTACHMENT_RE = re.compile(r"filename\*?=(?:UTF-8''|\"?)([^\";]+)", re.I)


class DvcPersonalPortal(DvcPortal):
    """Tờ khai của tài khoản cá nhân trên Dịch vụ công.

    Cột bảng giống hệt luồng DVC doanh nghiệp; chỉ khác nguồn ghi vào metadata,
    nên chỉ cần đổi ``source`` và giữ nguồn đó khi portal cha đọc bảng.
    """

    source = SOURCE_DVC_PERSONAL
    detail_loai = ""

    def _page_result(self, response) -> PageResult:
        result = super()._page_result(response)
        for record in result.records:
            record.nguon = self.source
        return result


class CanhanNoticePortal(Portal):
    """Thông báo của cơ quan thuế cho tài khoản cá nhân.

    Cổng ``canhan.gdt.gov.vn`` dùng luồng DSE riêng: SSO từ Dịch vụ công, một
    chuỗi form ``mainForm`` để mở phiên, rồi form ``frmtcuu`` cho tra cứu và tải.
    Tệp trả về là PDF; được gói trong ZIP ngay tại đây để phần lưu file dùng chung.
    """

    source = SOURCE_CANHAN
    detail_loai = ""
    #: Trang cá nhân không dùng CSRF token của DVC khi tải.
    csrf_optional = True

    def __init__(
        self,
        http: HttpClient,
        captcha,
        settings,
        csrf: str = "",
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(http, captcha, settings, logger)
        self.csrf = csrf
        self._page_html = ""
        self._page_url = CANHAN_REQUEST
        #: Trang đầu dùng form ``frm``; trang kết quả dùng ``frmtcuu``.
        self._form_id = "frmtcuu"
        self._logged_in = False

    # --- Mở phiên qua SSO + form DSE ---
    def login(self) -> None:
        """Vào cổng cá nhân bằng SSO và mở trang tra cứu thông báo."""
        if self._logged_in:
            return

        response = self.http.post(
            DVC_SSO_REDIRECT,
            params={"module": DVC_SSO_CANHAN_MODULE},
            headers=self.xhr_headers(
                headers={
                    "Origin": ORIGIN,
                    "Referer": self.landing_url,
                    "X-Requested-With": "XMLHttpRequest",
                    "X-XSRF-TOKEN": self.csrf,
                }
            ),
        )
        url = unescape(response.text.strip())
        if response.status_code != 200 or not url.startswith(f"{CANHAN_ORIGIN}/"):
            raise LoginError(
                "Không lấy được đường dẫn SSO sang cổng cá nhân "
                f"(HTTP={response.status_code}, {response.text[:120]!r})"
            )

        page = self.http.get(
            url,
            headers=build_page_headers(
                profile=self.profile, site="none", headers={"Referer": f"{ORIGIN}/"}
            ),
        )
        redirect = _js_redirect(page.text)
        if redirect:
            page = self.http.get(
                redirect,
                headers=build_page_headers(
                    profile=self.profile, headers={"Referer": page.url}
                ),
            )

        page = self._submit_form(page, "mainForm", {})
        page = self._submit_form(
            page,
            "mainForm",
            {"dse_operationName": _SEARCH_OPERATION, "dse_nextEventName": "start"},
        )
        try:
            self._form_id = _notice_form_id(page.text)
        except LoginError as error:
            raise LoginError(
                "Đã vào cổng cá nhân nhưng không thấy form tra cứu thông báo; "
                "có thể SSO hết hạn hoặc tài khoản không có quyền"
            ) from error
        self._page_html = page.text
        self._page_url = page.url or CANHAN_REQUEST
        self._logged_in = True
        self.logger.info("ĐÃ VÀO CỔNG THÔNG BÁO CÁ NHÂN (SSO module=%s)", DVC_SSO_CANHAN_MODULE)

    def _submit_form(self, page, form_id: str, overrides: Mapping[str, object]):
        action, fields = _form(page.text, form_id)
        fields.update({key: str(value) for key, value in overrides.items()})
        return self.http.post(
            action,
            data=fields,
            headers=self.xhr_headers(
                accept="text/html,application/xhtml+xml,*/*;q=0.8",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": CANHAN_ORIGIN,
                    "Referer": page.url or CANHAN_REQUEST,
                },
            ),
        )

    # --- Giai đoạn 3: tra cứu thông báo ---
    def search(self, period: SearchPeriod, page: int) -> PageResult:
        self.login()
        action, fields = _form(self._page_html, self._form_id)
        fields.update(
            {
                "dse_operationName": _SEARCH_OPERATION,
                "dse_processorState": _SEARCH_STATE,
                "dse_nextEventName": "ok",
                "maGDichArr": _EMPTY_TRANSACTION_IDS,
                "idHso": "",
                "cboThongBao": "",
                "_ngaygui": format_date(period.start),
                "_denngay": format_date(period.end),
            }
        )
        if page > 1:
            fields["pn"] = str(page)

        response = self.http.post(
            action,
            data=fields,
            headers=self.xhr_headers(
                accept="text/html,application/xhtml+xml,*/*;q=0.8",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": CANHAN_ORIGIN,
                    "Referer": self._page_url or CANHAN_REQUEST,
                },
            ),
        )
        if response.status_code != 200:
            return PageResult(http_status=response.status_code)
        # Không thay trang tốt bằng trang lỗi/hết phiên HTTP 200.
        if "frmtcuu" not in response.text and "downloadGNT(" not in response.text:
            self.logger.warning(
                "Cổng cá nhân không trả bảng thông báo/form tra cứu; có thể đã hết phiên"
            )
            return PageResult(http_status=response.status_code)

        self._page_html = response.text
        self._page_url = response.url or action
        self._form_id = _notice_form_id(response.text)
        return PageResult(
            records=parse_records(response.text, self.source),
            total_pages=page_count(response.text, self.source),
            http_status=response.status_code,
        )

    # --- Giai đoạn 4: tải PDF thông báo ---
    def fetch_detail_csrf(self, record: CaseRecord) -> tuple[str, str]:
        """Cổng cá nhân không dùng CSRF; trả URL tham chiếu cho ``download``."""
        return f"{CANHAN_REQUEST}?idTBao={record.ma_ho_so}", ""

    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        action, fields = _form(self._page_html, _notice_form_id(self._page_html))
        fields.update(
            {
                "dse_nextEventName": "download",
                "idTBao": record.ma_ho_so,
                "loaitbao": record.ma_loai_thong_bao,
            }
        )
        response = self.http.post(
            action,
            data=fields,
            headers=self.xhr_headers(
                accept="*/*",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": CANHAN_ORIGIN,
                    "Referer": self._page_url or CANHAN_REQUEST,
                },
            ),
        )
        if response.status_code != 200:
            return response
        if "text/html" in response.headers.get("content-type", "").lower():
            self.logger.error(
                "Cổng cá nhân trả HTML thay vì tệp thông báo %s (hết phiên?)",
                record.ma_ho_so,
            )
            return response
        return _NoticeZipResponse(record, response)


def _js_redirect(html: str) -> str:
    """URL mà trang DSE tự chuyển hướng bằng JavaScript, hoặc chuỗi rỗng."""
    match = _JS_REDIRECT_RE.search(html)
    return urljoin(f"{CANHAN_BASE}/", unescape(match.group(1))) if match else ""


def _notice_form_id(html: str) -> str:
    """Id form tra cứu/tải thông báo trên trang cổng cá nhân.

    Trang tìm kiếm ban đầu dùng ``frm``; trang kết quả dùng ``frmtcuu`` (có thêm
    ``idTBao``/``loaitbao``). Ưu tiên form kết quả khi có cả hai.
    """
    soup = BeautifulSoup(html, "html.parser")
    for candidate in ("frmtcuu", "frm"):
        if soup.find("form", id=candidate) is not None:
            return candidate
    raise LoginError("Không tìm thấy form tra cứu thông báo trên cổng cá nhân")


def _form(html: str, form_id: str) -> tuple[str, dict[str, str]]:
    """Action và toàn bộ ô nhập của một form trên cổng cá nhân."""
    form = BeautifulSoup(html, "html.parser").find("form", id=form_id)
    if form is None:
        raise LoginError(f"Không tìm thấy form id={form_id!r} trên cổng cá nhân")
    action = urljoin(f"{CANHAN_BASE}/", str(form.get("action") or "Request"))
    fields: dict[str, str] = {}
    for field in form.find_all(["input", "select"]):
        name = field.get("name")
        if not name:
            continue
        if field.name == "select":
            chosen = field.find("option", selected=True) or field.find("option")
            fields[str(name)] = str(chosen.get("value") or "") if chosen else ""
        else:
            fields[str(name)] = str(field.get("value") or "")
    return action, fields


def _attachment_name(response) -> str:
    disposition = response.headers.get("content-disposition", "")
    match = _ATTACHMENT_RE.search(disposition)
    return unescape(match.group(1)).strip() if match else ""


class _NoticeZipResponse:
    """PDF thông báo gói trong ZIP, cùng hình dạng JSON base64 như cổng DVC.

    ``decode_zip_bytes`` thử ``response.json()`` trước, nên phần lưu file không
    phải biết nguồn nào trả XML hay PDF.
    """

    def __init__(self, record: CaseRecord, response) -> None:
        name = _attachment_name(response) or f"{record.ma_ho_so}.pdf"
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(safe_filename_part(name, 80), response.content)
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


__all__ = ["CanhanNoticePortal", "DvcPersonalPortal"]
