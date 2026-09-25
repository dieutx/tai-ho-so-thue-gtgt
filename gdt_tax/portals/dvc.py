"""Nguồn Dịch vụ công — hồ sơ nộp từ ``01/07/2025``.

* tra cứu: ``GET /ho-so/search`` (tham số trên query string, cần CAPTCHA)
* tải ZIP: kiểm tra ``GET /tchs/validateIdTkhai`` rồi ``POST /tchs/downloadhoso``;
  nếu cổng không còn hỗ trợ kiểm tra AJAX thì lùi về form ``POST /downloadhoso``.
"""

from __future__ import annotations

from ..constants import (
    DEFAULT_HEADERS,
    DVC_DOWNLOAD,
    DVC_DOWNLOAD_FORM,
    DVC_SEARCH,
    DVC_VALIDATE,
    ORIGIN,
    SOURCE_DVC,
)
from ..dates import format_date
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
            headers={
                **self.base_headers(),
                "HX-Request": "true",
                "HX-Target": "table-container",
                "HX-Current-URL": self.landing_url,
                "Accept": "text/html-partial",
                "Referer": self.landing_url,
            },
        )
        return self._page_result(response)

    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        validation = self.http.get(
            DVC_VALIDATE,
            params={"idTKhai": record.ma_ho_so},
            headers={
                **DEFAULT_HEADERS,
                "Accept": "*/*",
                "Origin": ORIGIN,
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": csrf,
                "Referer": detail_url,
            },
        )
        if validation.status_code == 200 and validation.text.strip() == "200":
            return self.http.post(
                DVC_DOWNLOAD,
                json={"maHoSo": record.ma_ho_so},
                headers={
                    **DEFAULT_HEADERS,
                    "Accept": "*/*",
                    "Content-Type": "application/json",
                    "Origin": ORIGIN,
                    "X-Requested-With": "XMLHttpRequest",
                    "X-XSRF-TOKEN": csrf,
                    "Referer": detail_url,
                },
            )

        self.logger.warning(
            "Kiểm tra AJAX không khả dụng (HTTP=%s, %r); thử form tải dự phòng.",
            validation.status_code,
            validation.text[:100],
        )
        return self.http.post(
            DVC_DOWNLOAD_FORM,
            data={"_csrf": csrf, "mahoso": record.ma_ho_so},
            headers={
                **DEFAULT_HEADERS,
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": ORIGIN,
                "Referer": detail_url,
            },
        )


__all__ = ["DvcPortal"]
