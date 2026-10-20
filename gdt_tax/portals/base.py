"""Giao diện chung cho một nguồn dữ liệu trên cổng Dịch vụ công.

Mỗi nguồn (DVC, ETAX) khác nhau ở ba điểm: endpoint tra cứu, cách gọi endpoint
tải ZIP, và tham số ``loai`` của trang chi tiết. Mọi thứ còn lại — header, lấy
CAPTCHA, đọc bảng kết quả, lấy CSRF của trang chi tiết — đều ở lớp này.

Thêm nguồn mới: tạo lớp con của :class:`Portal`, cài ``source``, ``detail_loai``,
``search`` và ``download``, rồi đăng ký trong :mod:`gdt_tax.portals`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping

from ..captcha import fetch_captcha
from ..constants import CASE_DETAIL, LANDING
from ..csrf import csrf_token
from ..headers import build_page_headers, build_xhr_headers
from ..http import HttpClient
from ..models import CaseRecord, PageResult, SearchPeriod
from ..parsing import page_count, parse_record_table


class Portal(ABC):
    """Cách tra cứu và tải hồ sơ của một nguồn dữ liệu."""

    #: Giá trị nguồn dùng trong :class:`~gdt_tax.models.CaseRecord` (``DVC``/``ETAX``).
    source: str = ""
    #: Tham số ``loai`` của trang chi tiết hồ sơ.
    detail_loai: str = ""

    def __init__(self, http: HttpClient, captcha, settings, logger: logging.Logger | None = None) -> None:
        self.http = http
        self.captcha = captcha
        self.settings = settings
        self.logger = logger or logging.getLogger(f"gdt_tax.portal.{self.source.lower()}")

    @property
    def profile(self) -> str:
        """Bộ header đang dùng: ``browser`` (mặc định) hoặc ``minimal``."""
        return self.settings.header_profile

    # --- Phần từng nguồn phải tự cài ---
    @abstractmethod
    def search(self, period: SearchPeriod, page: int) -> PageResult:
        """Tra cứu một trang kết quả trong một đoạn ngày."""

    @abstractmethod
    def download(self, record: CaseRecord, detail_url: str, csrf: str):
        """Gọi endpoint tải ZIP và trả về phản hồi HTTP."""

    # --- Phần dùng chung ---
    @property
    def landing_url(self) -> str:
        return self.http.url(LANDING)

    def page_headers(
        self, *, site: str = "same-origin", headers: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        """Header cho một lần mở trang HTML; xem :func:`gdt_tax.headers.build_page_headers`."""
        return build_page_headers(profile=self.profile, site=site, headers=headers)

    def xhr_headers(
        self, *, accept: str = "*/*", headers: Mapping[str, str] | None = None
    ) -> dict[str, str]:
        """Header cho request AJAX/HTMX; xem :func:`gdt_tax.headers.build_xhr_headers`."""
        return build_xhr_headers(profile=self.profile, accept=accept, headers=headers)

    def captcha_text(self) -> str:
        """Lấy ảnh CAPTCHA tra cứu và nhờ solver hiện hành đọc mã."""
        image = fetch_captcha(self.http, "search", logger=self.logger, profile=self.profile)
        return self.captcha.solve(image) if image else ""

    def detail_url(self, record: CaseRecord) -> str:
        """URL trang chi tiết hồ sơ (nơi lấy CSRF token để tải)."""
        path = CASE_DETAIL.format(case_id=record.ma_ho_so)
        return f"{self.http.url(path)}?loai={self.detail_loai}"

    def fetch_detail_csrf(self, record: CaseRecord) -> tuple[str, str]:
        """Mở trang chi tiết và lấy token CSRF của form tải xuống."""
        url = self.detail_url(record)
        response = self.http.get(url, headers=self.page_headers(headers={"Referer": self.landing_url}))
        csrf = csrf_token(response.text) if response.status_code == 200 else ""
        return url, csrf

    def _page_result(self, response) -> PageResult:
        if response.status_code != 200:
            return PageResult(http_status=response.status_code)
        parsed = parse_record_table(response.text, self.source)
        result = PageResult(
            records=parsed.records,
            total_pages=page_count(response.text, self.source),
            http_status=response.status_code,
            diagnostics=parsed.diagnostics,
        )
        # Optional GUI feedback; CLI solvers keep their existing behavior.
        if parsed.diagnostics.complete:
            feedback = getattr(self.captcha, "accepted", None)
            if callable(feedback):
                feedback()
        elif parsed.diagnostics.status == "CAPTCHA_INVALID":
            feedback = getattr(self.captcha, "rejected", None)
            if callable(feedback):
                feedback()
        return result


__all__ = ["Portal"]
