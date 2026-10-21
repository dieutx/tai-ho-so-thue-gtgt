"""Nguồn Dịch vụ công — hồ sơ nộp từ ``01/07/2025``.

* tra cứu: ``GET /ho-so/search`` (tham số trên query string, cần CAPTCHA)
* tải ZIP: kiểm tra ``GET /tchs/validateIdTkhai`` rồi ``POST /tchs/downloadhoso``;
  nếu cổng không còn hỗ trợ kiểm tra AJAX thì lùi về form ``POST /downloadhoso``.
"""

from __future__ import annotations

from ..constants import (
    DVC_DOWNLOAD,
    DVC_DOWNLOAD_FORM,
    DVC_NOTICE_DOWNLOAD,
    DVC_NOTICE_DOWNLOAD_TDT,
    DVC_SEARCH,
    DVC_VALIDATE,
    ORIGIN,
    SOURCE_DVC,
)
from ..dates import format_date
from ..dvc_notices import DvcNotice, NoticeFile, decode_notice_response, parse_notices
from ..models import CaseRecord, PageResult, SearchPeriod
from .base import Portal


class DvcPortal(Portal):
    """Tra cứu và tải hồ sơ từ luồng Dịch vụ công."""

    source = SOURCE_DVC
    detail_loai = ""

    def search(self, period: SearchPeriod, page: int) -> PageResult:
        response = self.http.get(
            DVC_SEARCH,
            params={
                "maNghiepVu": "",
                "maTTHC": "",
                "maToKhai": "",
                "maHoSo": "",
                "tuNgay": format_date(period.start),
                "denNgay": format_date(period.end),
                "scope_tdt1": "SELF",
                "mstUyQuyen_tdt1": "",
                "captcha": self.captcha_text(),
                "page": page,
                "size": self.settings.page_size,
            },
            headers=self.xhr_headers(
                accept="text/html-partial",
                headers={
                    "HX-Request": "true",
                    "HX-Target": "table-container",
                    "HX-Current-URL": self.landing_url,
                    "Referer": self.landing_url,
                },
            ),
        )
        return self._page_result(response)

    def fetch_notices(self) -> list[DvcNotice]:
        """Đọc danh sách thông báo từ HTML trang chi tiết vừa mở."""
        return parse_notices(self.detail_html)

    def download_notice(
        self, notice: DvcNotice, detail_url: str, csrf: str
    ) -> NoticeFile | None:
        """Tải một thông báo đính kèm; trả ``None`` khi cổng không trả tệp hợp lệ."""
        path = DVC_NOTICE_DOWNLOAD_TDT if notice.is_tdt else DVC_NOTICE_DOWNLOAD
        params = {"loaiTraCuu": notice.loai_tra_cuu} if notice.is_tdt else None
        response = self.http.post(
            path,
            params=params,
            json={"idTbao": notice.id, "loaiTBao": notice.loai_tbao},
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
        payload = decode_notice_response(response)
        if payload is None:
            self.logger.warning(
                "Thông báo đính kèm %s không tải được (HTTP=%s); có thể hết phiên hoặc cổng đổi định dạng.",
                notice.id,
                getattr(response, "status_code", "-"),
            )
        return payload

    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        validation = self.http.get(
            DVC_VALIDATE,
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
        if validation.status_code == 200 and validation.text.strip() == "200":
            return self.http.post(
                DVC_DOWNLOAD,
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

        self.logger.warning(
            "Kiểm tra AJAX không khả dụng (HTTP=%s, %r); thử form tải dự phòng.",
            validation.status_code,
            validation.text[:100],
        )
        # Đây là form submit thật (không phải AJAX), nên dùng bộ header điều hướng.
        return self.http.post(
            DVC_DOWNLOAD_FORM,
            data={"_csrf": csrf, "mahoso": record.ma_ho_so},
            headers=self.page_headers(
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": ORIGIN,
                    "Referer": detail_url,
                }
            ),
        )


__all__ = ["DvcPortal"]
