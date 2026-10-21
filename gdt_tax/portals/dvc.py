"""Nguồn Dịch vụ công — hồ sơ nộp từ ``01/07/2025``.

* tra cứu: ``GET /ho-so/search`` (tham số trên query string, cần CAPTCHA)
* tải ZIP: kiểm tra ``GET /tchs/validateIdTkhai`` rồi ``POST /tchs/downloadhoso``;
  nếu cổng không còn hỗ trợ kiểm tra AJAX thì lùi về form ``POST /downloadhoso``.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from ..auth_outcomes import raise_terminal
from ..constants import (
    ORIGIN,
    SOURCE_DVC,
)
from ..dates import format_date
from ..dvc_notices import decode_notice_response, parse_notice_list
from ..models import CaseRecord, PageResult, SearchPeriod
from .base import Portal


class DvcPortal(Portal):
    """Tra cứu và tải hồ sơ từ luồng Dịch vụ công."""

    source = SOURCE_DVC
    detail_loai = ""

    def search(self, period: SearchPeriod, page: int) -> PageResult:
        response = self.http.get(
            self.capabilities.search_endpoint,
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
        if validation.status_code == 200 and validation.text.strip() == "200":
            return self.http.post(
                self.capabilities.download_endpoint,
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
            "Kiểm tra AJAX không khả dụng (HTTP=%s); thử form tải dự phòng.",
            validation.status_code,
        )

        # Đây là form submit thật (không phải AJAX), nên dùng bộ header điều hướng.
        return self.http.post(
            self.capabilities.download_form_endpoint,
            data={"_csrf": csrf, "mahoso": record.ma_ho_so},
            headers=self.page_headers(
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": ORIGIN,
                    "Referer": detail_url,
                }
            ),
        )

    def fetch_notice_list(self):
        return parse_notice_list(self.detail_html)

    def fetch_notices(self):
        return self.fetch_notice_list().notices

    def download_notice(self, notice, detail_url: str, csrf: str):
        path = '/tchs/downloadthongbao-tdt' if notice.is_tdt else '/tchs/downloadthongbao'
        response = self.http.post(path,
            params={'loaiTraCuu': notice.loai_tra_cuu} if notice.is_tdt else None,
            json={'idTbao': notice.id, 'loaiTBao': notice.loai_tbao},
            headers=self.xhr_headers(headers={'Content-Type': 'application/json',
                'Origin': ORIGIN, 'Referer': detail_url, 'X-Requested-With': 'XMLHttpRequest',
                'X-XSRF-TOKEN': csrf}))
        raise_terminal(response, 'DVC', authenticated=True)
        return decode_notice_response(response)


__all__ = ["DvcPortal"]
