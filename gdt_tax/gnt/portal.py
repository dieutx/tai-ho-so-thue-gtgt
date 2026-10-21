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
    GNT_TYPE_TAX,
)
from ..dates import format_date
from ..errors import LegacyEtaxError
from ..integrity import validate_xml
from ..legacy_navigation import LegacyBusinessPortal
from ..models import SearchPeriod
from ..table_contracts import ParseDiagnostics
from .models import GiayNopTien, GntPageResult
from .parsing import gnt_page_count, parse_gnt_table

#: Trang trả lại bảng rỗng kèm câu này khi khoảng ngày không có GNT nào.
_EMPTY_MARKERS = ("Chưa có giấy nộp tiền", "Không có dữ liệu", "không có giấy nộp tiền")


def is_gnt_xml(data: bytes) -> bool:
    """Dữ liệu có phải XML giấy nộp tiền (không phải HTML lỗi/hết phiên)."""
    return validate_xml(data, "gnt").ok


class GntPortal(LegacyBusinessPortal):
    """Portal giấy nộp tiền: dùng lại đăng nhập legacy, thêm tra cứu/tải GNT."""

    source = 'GNT'

    def _open_gnt_page(self) -> None:
        """Mở trang tra cứu GNT (form ``reportForm``).

        Cổng có lúc trả trang chuyển tiếp hoặc form với id khác, nên dùng helper
        chung của portal legacy thay vì chỉ so chuỗi ``reportForm``.
        """
        response, form_id = self._open_operation_page(
            self.capabilities.operation, self.capabilities.form_id, "giấy nộp tiền"
        )
        self._search_form_id = form_id
        self._search_page_html = response.text
        self._search_page_url = response.url

    def search_gnt(self, period: SearchPeriod, page: int) -> GntPageResult:
        """Tra cứu một trang GNT theo ngày lập, lọc GNT nộp tại Cổng eTax."""
        self.login()
        if not self._search_page_html:
            self._open_gnt_page()
        response = self._post_form(
            self._search_page_html,
            self._search_form_id,
            self._search_page_url,
            {
                "dse_operationName": self.capabilities.operation,
                "dse_nextEventName": self.capabilities.query_event,
                "type_tax": GNT_TYPE_TAX,
                self.capabilities.page_parameter: page,
                "ngay_lap_tu_ngay": format_date(period.start),
                "ngay_lap_den_ngay": format_date(period.end),
            },
        )
        if response.status_code != 200:
            return GntPageResult(http_status=response.status_code)
        empty = any(marker in response.text for marker in _EMPTY_MARKERS)
        form_id = self._form_id_for_operation(response.text, self.capabilities.operation, self._search_form_id)
        if not form_id or (self.capabilities.table_id not in response.text and not empty):
            if self.session_state is not None:
                raise LegacyEtaxError(
                    "Cổng trả HTTP 200 nhưng thiếu bảng/form giấy nộp tiền. "
                    "Hãy thử lại; nếu vẫn lỗi, đăng xuất rồi đăng nhập hoặc xem nhật ký."
                )
            self.logger.warning(
                "SCHEMA_CHANGED: legacy thiếu bảng hoặc form GNT"
            )
            return GntPageResult(http_status=response.status_code, diagnostics=ParseDiagnostics(reasons=["RESULT_FORM_OR_TABLE_MISSING"]))
        # Chỉ thay form đang có khi trang thực sự là kết quả GNT (giữ được phiên).
        self._search_form_id = form_id
        self._search_page_html = response.text
        self._search_page_url = response.url
        parsed = parse_gnt_table(response.text, schema=self.capabilities.schema)
        return GntPageResult(
            records=parsed.records,
            total_pages=gnt_page_count(response.text, table_id=self.capabilities.table_id),
            http_status=response.status_code,
            diagnostics=parsed.diagnostics,
        )

    def download_gnt(self, record: GiayNopTien) -> bytes | None:
        """Tải XML giấy nộp tiền; trả ``None`` khi cổng trả HTML (lỗi/hết phiên)."""
        self.last_download_error = ""
        if not self._search_page_html:
            raise LegacyEtaxError("Chưa có trang kết quả GNT để tải theo")
        response = self._post_form(
            self._search_page_html,
            self._search_form_id,
            self._search_page_url,
            {
                "dse_operationName": self.capabilities.operation,
                "dse_nextEventName": self.capabilities.download_event,
                "type_tax": GNT_TYPE_TAX,
                "ctuId": record.ctu_id,
                # Hai trường này có trong reportForm/đi kèm request thật của cổng.
                "isReport": "N",
                "type": "pdf",
            },
        )
        if response.status_code != 200:
            self.last_download_error = f"Cổng trả HTTP {response.status_code} khi tải XML; kiểm tra kết nối hoặc phiên đăng nhập."
            return None
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type or not is_gnt_xml(response.content):
            self.last_download_error = "Cổng trả HTML hoặc dữ liệu không phải XML hoàn chỉnh; có thể phiên hết hạn hoặc cổng đổi định dạng."
            self.logger.error(
                "GNT %s không tải được XML (hết phiên hoặc cổng đổi định dạng)",
                record.ctu_id,
            )
            return None
        return response.content


__all__ = ["GntPortal", "is_gnt_xml"]
