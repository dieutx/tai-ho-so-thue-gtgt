"""Tra cứu và tải thông báo của cơ quan thuế trên trang Thuế điện tử cũ.

Dùng chung phiên đăng nhập DSE với tờ khai/GNT nhưng là một operation khác::

    tracuuTBThueKhacProc (form ``tKhaiForm``) → query (theo ngày nộp)
      → bảng ``tbl_tracuu``
      → tracuuTBThueKhacProc + dse_nextEventName=download + messageId → PDF

Phân trang giống tờ khai thông thường: trang 1 bằng POST form, các trang sau bằng
GET kèm ``pn`` (đúng như ``gotoPage`` trên trang thật).
"""

from __future__ import annotations

from ..constants import LEGACY_ETAX_BASE, TB_FORM_ID, TB_OPERATION, TB_RESULT_TABLE_ID
from ..dates import format_date
from ..errors import LegacyEtaxError
from ..headers import build_page_headers
from ..models import SearchPeriod
from ..portals.etax_legacy import EtaxLegacyPortal, _form_fields
from .models import TbPageResult, ThongBao
from .parsing import parse_tb_records, tb_page_count

#: Trang trả lại bảng rỗng kèm một trong các câu này khi không có thông báo nào.
_EMPTY_MARKERS = (
    "Không tìm thấy thông báo",
    "không có thông báo",
    "Chưa có thông báo",
    "Không có dữ liệu",
)

#: Khóa phiên cần giữ khi dựng URL phân trang.
_SESSION_KEYS = (
    "dse_sessionId",
    "dse_applicationId",
    "dse_pageId",
    "dse_processorState",
    "dse_processorId",
)


def is_tb_pdf(data: bytes) -> bool:
    """Dữ liệu có phải PDF (không phải HTML lỗi/hết phiên)."""
    return data.lstrip()[:5] == b"%PDF-"


class TbPortal(EtaxLegacyPortal):
    """Portal thông báo: dùng lại đăng nhập legacy, thêm tra cứu/tải TB."""

    def _open_tb_page(self) -> None:
        """Mở trang tra cứu thông báo (form ``tKhaiForm``)."""
        if not self.dse_session_id or not self.home_page_id:
            raise LegacyEtaxError("Chưa đăng nhập legacy")
        response = self.http.get(
            f"{LEGACY_ETAX_BASE}/Request",
            params={
                "dse_sessionId": self.dse_session_id,
                "dse_applicationId": "-1",
                "dse_pageId": self.home_page_id,
                "dse_operationName": TB_OPERATION,
                "dse_processorState": "initial",
                "dse_nextEventName": "start",
            },
            headers=build_page_headers(profile=self.profile),
        )
        if response.status_code != 200 or TB_FORM_ID not in response.text:
            raise LegacyEtaxError("Không mở được trang tra cứu thông báo legacy")
        self._search_page_html = response.text
        self._search_page_url = response.url

    def _query_page_one(self, period: SearchPeriod):
        return self._post_form(
            self._search_page_html,
            TB_FORM_ID,
            self._search_page_url,
            {
                "dse_operationName": TB_OPERATION,
                "dse_nextEventName": "query",
                "pageNumber": "1",
                "tuNgayNop": format_date(period.start),
                "denNgayNop": format_date(period.end),
            },
        )

    def _query_page(self, page: int):
        """Phân trang: GET kèm ``pn`` theo các khóa phiên của trang kết quả hiện tại."""
        _, fields = _form_fields(self._search_page_html, TB_FORM_ID)
        params = {key: fields[key] for key in _SESSION_KEYS if fields.get(key)}
        params.update(
            {
                "dse_operationName": TB_OPERATION,
                "dse_errorPage": "error_page.jsp",
                "dse_nextEventName": "query",
                "pn": str(page),
            }
        )
        return self.http.get(
            f"{LEGACY_ETAX_BASE}/Request",
            params=params,
            headers=build_page_headers(profile=self.profile),
        )

    def search_tb(self, period: SearchPeriod, page: int) -> TbPageResult:
        """Tra cứu một trang thông báo theo ngày nộp."""
        self.login()
        if not self._search_page_html:
            self._open_tb_page()
        response = self._query_page_one(period) if page == 1 else self._query_page(page)
        if response.status_code != 200:
            return TbPageResult(http_status=response.status_code)
        empty = any(marker in response.text for marker in _EMPTY_MARKERS)
        if TB_FORM_ID not in response.text or (
            TB_RESULT_TABLE_ID not in response.text and not empty
        ):
            self.logger.warning(
                "Legacy không trả bảng thông báo/form tra cứu; có thể đã hết phiên"
            )
            return TbPageResult(http_status=response.status_code)
        self._search_page_html = response.text
        self._search_page_url = response.url
        return TbPageResult(
            records=parse_tb_records(response.text),
            total_pages=tb_page_count(response.text),
            http_status=response.status_code,
        )

    def download_tb(self, record: ThongBao) -> bytes | None:
        """Tải PDF thông báo; trả ``None`` khi cổng trả HTML (lỗi/hết phiên)."""
        if not self._search_page_html:
            raise LegacyEtaxError("Chưa có trang kết quả thông báo để tải theo")
        response = self._post_form(
            self._search_page_html,
            TB_FORM_ID,
            self._search_page_url,
            {
                "dse_operationName": TB_OPERATION,
                "dse_nextEventName": "download",
                "messageId": record.message_id,
                "ma_tbao": record.ma_tbao,
            },
        )
        if response.status_code != 200:
            return None
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type or not is_tb_pdf(response.content):
            self.logger.error(
                "Thông báo %s không tải được PDF (hết phiên hoặc cổng đổi định dạng)",
                record.message_id,
            )
            return None
        return response.content


__all__ = ["TbPortal", "is_tb_pdf"]
