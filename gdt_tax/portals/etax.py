"""Nguồn Thuế điện tử — tờ khai nộp trước ``01/07/2025``.

Hai endpoint khác biệt so với nguồn DVC:

* tra cứu: ``POST /tchs/thuedientu`` (form-urlencoded, cần ``_csrf`` và CAPTCHA)
* tải ZIP: ``POST /tchs/downloadhoso-tdt?loaiTraCuu=ETAX`` (JSON ``{"maHoSo": ...}``)
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from ..constants import (
    ORIGIN,
    SOURCE_ETAX,
)
from ..dates import format_date
from ..http import HttpClient
from ..models import CaseRecord, PageResult, SearchPeriod
from .base import Portal


class EtaxPortal(Portal):
    """Tra cứu và tải hồ sơ từ luồng Thuế điện tử."""

    source = SOURCE_ETAX
    detail_loai = SOURCE_ETAX

    def __init__(self, http: HttpClient, captcha, settings, csrf: str = "", logger=None) -> None:
        super().__init__(http, captcha, settings, logger)
        self.csrf = csrf

    def search(self, period: SearchPeriod, page: int) -> PageResult:
        response = self.http.post(
            self.capabilities.search_endpoint,
            data={
                "_csrf": self.csrf,
                self.capabilities.page_parameter: page,
                "size": self.settings.page_size,
                "maToKhai_tdt": "",
                "maGiaoDichTthc_tdt": "",
                "tuNgay_tdt": format_date(period.start),
                "denNgay_tdt": format_date(period.end),
                "scope_tdt2": "SELF",
                "mstUyQuyen_tdt2": "",
                "captcha": self.captcha_text(),
                "btnSearch_tdt": "",
            },
            headers=self.xhr_headers(
                accept="text/html-partial",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "HX-Current-URL": self.landing_url,
                    "HX-Request": "true",
                    "HX-Target": self.capabilities.result_container,
                    "HX-Trigger": self.capabilities.form_id,
                    "Origin": ORIGIN,
                    "Referer": self.landing_url,
                    "X-XSRF-TOKEN": self.csrf,
                },
            ),
        )
        result = self._page_result(response)
        soup = BeautifulSoup(response.text, 'lxml')
        total = soup.find(id=self.capabilities.page_total_id)
        control = soup.find(id=self.capabilities.page_input_id)
        count = total.get_text(strip=True) if total else ''
        count = count or str(control.get('max', '')) if control else count
        result.total_pages = int(count) if count.isdigit() else None
        return result

    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        return self.http.post(
            self.capabilities.download_endpoint,
            params={"loaiTraCuu": SOURCE_ETAX},
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


__all__ = ["EtaxPortal"]
