"""Tra cứu và tải giấy nộp tiền trên trang Thuế điện tử cũ (etaxnnt).

Giấy nộp tiền dùng **cùng phiên đăng nhập DSE** với tờ khai legacy nhưng là một
operation khác::

    corpQueryTaxProc (form ``reportForm``) → query (theo ngày lập GNT)
      → bảng ``data_content_onday``
      → corpQueryTaxProc + dse_nextEventName=download + ctuId → XML <CHUNGTU>

Lớp :class:`GntPortal` kế thừa :class:`~gdt_tax.portals.etax_legacy.EtaxLegacyPortal`
để dùng lại toàn bộ luồng đăng nhập (EstablishSession → loginForm + CAPTCHA →
corporateHomeProc) và chỉ thêm hai bước tra cứu/tải của GNT. Vì vậy công cụ chỉ
đăng nhập trang cũ **một lần** cho cả tờ khai lẫn giấy nộp tiền khi chạy trong
cùng tiến trình.
"""

from __future__ import annotations

from ..constants import (
    GNT_FORM_ID,
    GNT_OPERATION,
    GNT_RESULT_TABLE_ID,
    GNT_TYPE_TAX,
    LEGACY_ETAX_BASE,
)
from ..dates import format_date
from ..errors import LegacyEtaxError
from ..headers import build_page_headers
from ..models import SearchPeriod
from ..portals.etax_legacy import EtaxLegacyPortal
from .models import GiayNopTien, GntPageResult
from .parsing import gnt_page_count, parse_gnt_records

#: Trang trả lại bảng rỗng kèm câu này khi khoảng ngày không có GNT nào.
_EMPTY_MARKERS = ("Chưa có giấy nộp tiền", "Không có dữ liệu", "không có giấy nộp tiền")


def is_gnt_xml(data: bytes) -> bool:
    """Dữ liệu có phải XML giấy nộp tiền (không phải HTML lỗi/hết phiên)."""
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    try:
        root = etree.fromstring(data, parser=parser)
    except (etree.XMLSyntaxError, ValueError, TypeError):
        return False
    name = etree.QName(root).localname.lower()
    return name not in {"html", "error"} and not root.getroottree().docinfo.doctype


class GntPortal(EtaxLegacyPortal):
    """Portal giấy nộp tiền: dùng lại đăng nhập legacy, thêm tra cứu/tải GNT."""

    def _open_gnt_page(self) -> None:
        """Mở trang tra cứu GNT (form ``reportForm``)."""
        if not self.dse_session_id or not self.home_page_id:
            raise LegacyEtaxError("Chưa đăng nhập legacy")
        response = self.http.get(
            f"{LEGACY_ETAX_BASE}/Request",
            params={
                "dse_sessionId": self.dse_session_id,
                "dse_applicationId": "-1",
                "dse_pageId": self.home_page_id,
                "dse_operationName": GNT_OPERATION,
                "dse_processorState": "initial",
                "dse_nextEventName": "start",
            },
            headers=build_page_headers(profile=self.profile),
        )
        if response.status_code != 200 or GNT_FORM_ID not in response.text:
            raise LegacyEtaxError("Không mở được trang tra cứu giấy nộp tiền legacy")
        self._search_page_html = response.text
        self._search_page_url = response.url

    def search_gnt(self, period: SearchPeriod, page: int) -> GntPageResult:
        """Tra cứu một trang GNT theo ngày lập, lọc GNT nộp tại Cổng eTax."""
        self.login()
        if not self._search_page_html:
            self._open_gnt_page()
        response = self._post_form(
            self._search_page_html,
            GNT_FORM_ID,
            self._search_page_url,
            {
                "dse_operationName": GNT_OPERATION,
                "dse_nextEventName": "query",
                "type_tax": GNT_TYPE_TAX,
                "pn": page,
                "ngay_lap_tu_ngay": format_date(period.start),
                "ngay_lap_den_ngay": format_date(period.end),
            },
        )
        if response.status_code != 200:
            return GntPageResult(http_status=response.status_code)
        empty = any(marker in response.text for marker in _EMPTY_MARKERS)
        if GNT_FORM_ID not in response.text or (
            GNT_RESULT_TABLE_ID not in response.text and not empty
        ):
            self.logger.warning(
                "Legacy không trả bảng GNT/form tra cứu; có thể đã hết phiên"
            )
            return GntPageResult(http_status=response.status_code)
        # Chỉ thay form đang có khi trang thực sự là kết quả GNT (giữ được phiên).
        self._search_page_html = response.text
        self._search_page_url = response.url
        return GntPageResult(
            records=parse_gnt_records(response.text),
            total_pages=gnt_page_count(response.text),
            http_status=response.status_code,
        )

    def download_gnt(self, record: GiayNopTien) -> bytes | None:
        """Tải XML giấy nộp tiền; trả ``None`` khi cổng trả HTML (lỗi/hết phiên)."""
        if not self._search_page_html:
            raise LegacyEtaxError("Chưa có trang kết quả GNT để tải theo")
        response = self._post_form(
            self._search_page_html,
            GNT_FORM_ID,
            self._search_page_url,
            {
                "dse_operationName": GNT_OPERATION,
                "dse_nextEventName": "download",
                "type_tax": GNT_TYPE_TAX,
                "ctuId": record.ctu_id,
                # Hai trường này có trong reportForm/đi kèm request thật của cổng.
                "isReport": "N",
                "type": "pdf",
            },
        )
        if response.status_code != 200:
            return None
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type or not is_gnt_xml(response.content):
            self.logger.error(
                "GNT %s không tải được XML (hết phiên hoặc cổng đổi định dạng)",
                record.ctu_id,
            )
            return None
        return response.content


__all__ = ["GntPortal", "is_gnt_xml"]
