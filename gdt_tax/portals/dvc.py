"""Nguồn Dịch vụ công — hồ sơ nộp từ ``01/07/2025``.

* tra cứu: ``GET /ho-so/search`` (tham số trên query string, cần CAPTCHA)
* tải ZIP: kiểm tra ``GET /tchs/validateIdTkhai`` rồi ``POST /tchs/downloadhoso``;
  nếu cổng không còn hỗ trợ kiểm tra AJAX thì lùi về form ``POST /downloadhoso``.
"""

from __future__ import annotations

import base64
import time

from bs4 import BeautifulSoup

from ..auth_outcomes import raise_terminal
from ..constants import (
    ORIGIN,
    SOURCE_DVC,
)
from ..contracts import DownloadArtifact
from ..dates import format_date
from ..dvc_notices import decode_notice_response, parse_notice_list
from ..errors import AttachmentDownloadError
from ..http_policy import DOWNLOAD_OPERATION, OperationPolicy
from ..models import CaseRecord, PageResult, SearchPeriod
from ..run_hooks import RunHooks
from .base import Portal


def json_wrapped_zip(response, record: CaseRecord) -> DownloadArtifact | None:
    """Cổng DVC có lúc trả ZIP bọc trong JSON base64 thay vì bytes ZIP.

    Đã gặp với hồ sơ ``01/TS``: ``POST /tchs/downloadhoso`` trả HTTP 200,
    ``content-type: application/json`` và body
    ``{"fileName": "files_<mã>.zip", "fileType": "application/zip", "content": "<base64>"}``.
    Không giải mã thì tệp bị coi là hỏng và hồ sơ mất tệp dù cổng có trả.
    """
    if getattr(response, "status_code", 0) != 200:
        return None
    try:
        payload = response.json()
    except (ValueError, AttributeError, TypeError):
        # ZIP nhị phân không parse được thành JSON: giữ nguyên phản hồi gốc.
        return None
    if not isinstance(payload, dict):
        return None
    encoded = payload.get("content")
    if not isinstance(encoded, str) or not encoded:
        return None
    if len(encoded) > (DOWNLOAD_OPERATION.max_bytes + 2) // 3 * 4:
        return None
    try:
        data = base64.b64decode("".join(encoded.split()), validate=True)
    except (ValueError, TypeError):
        return None
    if not data.startswith(b"PK"):
        return None
    return DownloadArtifact(data, "zip", "DECLARATION", record.key)


class DvcPortal(Portal):
    """Tra cứu và tải hồ sơ từ luồng Dịch vụ công."""

    source = SOURCE_DVC
    supports_case_search = True
    detail_loai = ""
    #: Kết quả dò khả năng AJAX chỉ cần biết một lần cho mỗi lượt chạy: cổng
    #: không đổi giữa hai hồ sơ, nên hồ sơ sau không phải gửi lại request dò.
    _ajax_validation: bool | None = None

    def _pause(self, seconds: float) -> None:
        hooks = getattr(self.http, "hooks", None)
        (hooks if isinstance(hooks, RunHooks) else RunHooks()).pause(seconds, time.sleep)

    def search(self, period: SearchPeriod, page: int, *, case_id: str = "") -> PageResult:
        response = self.http.get(
            self.capabilities.search_endpoint,
            params={
                "maNghiepVu": "",
                "maTTHC": "",
                "maToKhai": "",
                "maHoSo": case_id,
                "tuNgay": format_date(period.start),
                "denNgay": format_date(period.end),
                "scope_tdt1": "SELF",
                "mstUyQuyen_tdt1": "",
                "captcha": self.captcha_text(),
                self.capabilities.page_parameter: page,
                "size": self.settings.page_size,
            },
            headers=self.xhr_headers(
                accept="text/html-partial",
                headers={
                    "HX-Request": "true",
                    "HX-Target": self.capabilities.result_container,
                    "HX-Trigger": self.capabilities.form_id,
                    "HX-Current-URL": self.landing_url,
                    "Referer": self.landing_url,
                },
            ),
        )
        result = self._page_result(response)
        soup = BeautifulSoup(response.text, 'lxml')
        total = soup.find(id=self.capabilities.page_total_id)
        control = soup.find(id=self.capabilities.page_input_id)
        count = total.get_text(strip=True) if total else str(control.get('max', '')) if control else ''
        result.total_pages = int(count) if count.isdigit() else None
        return result

    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        download_operation = OperationPolicy(
            'declaration-download', DOWNLOAD_OPERATION.max_bytes,
            retry_safe=True, minimum_attempts=6,
        )
        if self._ajax_validation is not True:
            validation = self.http.get(
                self.capabilities.validate_endpoint,
                params={"idTKhai": record.ma_ho_so},
                headers=self.xhr_headers(
                    headers={
                        "Origin": ORIGIN,
                        "Referer": detail_url,
                        "X-Requested-With": "XMLHttpRequest",
                        "X-XSRF-TOKEN": csrf,
                    }
                ),
            )
            raise_terminal(validation, 'DVC', authenticated=True)
            self._ajax_validation = validation.status_code == 200 and validation.text.strip() == "200"
        if self._ajax_validation:
            response = self.http.post(
                self.capabilities.download_endpoint,
                operation=download_operation,
                json={"maHoSo": record.ma_ho_so},
                headers=self.xhr_headers(
                    headers={
                        "Content-Type": "application/json",
                        "Origin": ORIGIN,
                        "Referer": detail_url,
                        "X-Requested-With": "XMLHttpRequest",
                        "X-XSRF-TOKEN": csrf,
                    }
                ),
            )
            raise_terminal(response, 'DVC', authenticated=True)
            artifact = json_wrapped_zip(response, record)
            return artifact if artifact is not None else response

        if self._ajax_validation is False:
            self.logger.warning("Kiểm tra AJAX không khả dụng; dùng form tải dự phòng.")

        # Đây là form submit thật (không phải AJAX), nên dùng bộ header điều hướng.
        response = self.http.post(
            self.capabilities.download_form_endpoint,
            operation=download_operation,
            data={"_csrf": csrf, "mahoso": record.ma_ho_so},
            headers=self.page_headers(
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": ORIGIN,
                    "Referer": detail_url,
                }
            ),
        )
        raise_terminal(response, 'DVC', authenticated=True)
        artifact = json_wrapped_zip(response, record)
        return artifact if artifact is not None else response

    def fetch_notice_list(self):
        return parse_notice_list(self.detail_html)

    def fetch_notices(self):
        return self.fetch_notice_list().notices

    def download_notice(self, notice, detail_url: str, csrf: str):
        path = '/tchs/downloadthongbao-tdt' if notice.is_tdt else '/tchs/downloadthongbao'
        for attempt in range(1, 4):
            response = self.http.post(path,
                # Cổng giới hạn riêng endpoint này: giữ 6 lượt nhưng tăng khoảng chờ
                # chậm (2 → 2,6 → 3,4s) thay vì 2 → 4 → 8 → 16 → 32s.
                operation=OperationPolicy('notice-download', DOWNLOAD_OPERATION.max_bytes,
                                          retry_safe=True, minimum_attempts=6,
                                          retry_growth=1.3),
                params={'loaiTraCuu': notice.loai_tra_cuu} if notice.is_tdt else None,
                json={'idTbao': notice.id, 'loaiTBao': notice.loai_tbao},
                headers=self.xhr_headers(headers={'Content-Type': 'application/json',
                    'Origin': ORIGIN, 'Referer': detail_url, 'X-Requested-With': 'XMLHttpRequest',
                    'X-XSRF-TOKEN': csrf}))
            raise_terminal(response, 'DVC', authenticated=True)
            if response.status_code == 429:
                # HttpClient đã tự chờ và thử lại 6 lượt cho 429; không lặp
                # thêm ở đây để tránh nhân đôi số request khi cổng đang bận.
                raise AttachmentDownloadError('ATTACHMENT_RATE_LIMITED',
                    'Cổng đang giới hạn tải thông báo (HTTP 429); đã chờ và thử lại theo giới hạn. Tệp hồ sơ chính được giữ nguyên.')
            if response.status_code != 200:
                raise AttachmentDownloadError('ATTACHMENT_HTTP_ERROR',
                    f'Cổng trả HTTP {response.status_code} khi tải thông báo; tệp hồ sơ chính được giữ nguyên.')
            payload = decode_notice_response(response)
            if payload is not None:
                return payload
            # Cổng có lúc trả HTTP 200 kèm body "Too Many Requests" thay vì 429.
            if b'too many requests' in (response.content or b'').lower():
                self.logger.warning(
                    'Cổng giới hạn tải thông báo %s (HTTP 200, Too Many Requests); thử lại %s/3',
                    notice.id, attempt,
                )
                if attempt < 3:
                    self._pause(min(2 * attempt, 6))
                continue
            # Nội dung hỏng/không đúng định dạng có thể do cổng trả tạm thời;
            # thử lại có giới hạn trước khi báo lỗi thật.
            self.logger.warning('Thông báo %s trả nội dung chưa đọc được (lần %s/3)', notice.id, attempt)
            if attempt < 3:
                self._pause(1.5)
        raise AttachmentDownloadError(
            'ATTACHMENT_INVALID_OR_RATE_LIMITED',
            'Cổng trả nội dung không đọc được hoặc giới hạn tải sau 3 lần thử; tệp hồ sơ chính được giữ nguyên.',
        )


__all__ = ["DvcPortal", "json_wrapped_zip"]
