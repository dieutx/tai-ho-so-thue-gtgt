"""Tra cứu và tải thông báo của cơ quan thuế trên trang Thuế điện tử cũ.

Dùng chung phiên đăng nhập DSE với tờ khai/GNT nhưng là một operation khác::

    tracuuTBThueKhacProc (form ``tKhaiForm``) → query (theo ngày nộp)
      → bảng ``tbl_tracuu``
      → tracuuTBThueKhacProc + dse_nextEventName=download + messageId → PDF

Phân trang giống tờ khai thông thường: trang 1 bằng POST form, các trang sau bằng
GET kèm ``pn`` (đúng như ``gotoPage`` trên trang thật).
"""

from __future__ import annotations

from ..auth_outcomes import raise_terminal
from ..dates import format_date
from ..errors import LegacyEtaxError
from ..headers import build_page_headers
from ..integrity import validate_pdf
from ..legacy_navigation import LegacyBusinessPortal, form_fields
from ..models import SearchPeriod
from ..table_contracts import ParseDiagnostics
from .models import TbPageResult, ThongBao
from .parsing import parse_tb_table, tb_page_count

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
    return validate_pdf(data).ok


class TbPortal(LegacyBusinessPortal):
    """Portal thông báo: dùng lại đăng nhập legacy, thêm tra cứu/tải TB."""

    source = 'TB'

    def _open_tb_page(self) -> None:
        """Mở trang tra cứu thông báo (form ``tKhaiForm``).

        Cổng có lúc trả trang chuyển tiếp hoặc form với id khác, nên dùng helper
        chung của portal legacy thay vì chỉ so chuỗi ``tKhaiForm``.
        """
        response, form_id = self._open_operation_page(
            self.capabilities.operation, self.capabilities.form_id, "thông báo"
        )
        self._search_form_id = form_id
        self._search_page_html = response.text
        self._search_page_url = response.url

    def _query_page_one(self, period: SearchPeriod):
        return self._post_form(
            self._search_page_html,
            self._search_form_id,
            self._search_page_url,
            {
                "dse_operationName": self.capabilities.operation,
                "dse_nextEventName": self.capabilities.query_event,
                "pageNumber": "1",
                "tuNgayNop": format_date(period.start),
                "denNgayNop": format_date(period.end),
            },
        )

    def _query_page(self, page: int):
        """Phân trang: GET kèm ``pn`` theo các khóa phiên của trang kết quả hiện tại."""
        _, fields = form_fields(self._search_page_html, self._search_form_id)
        params = {key: fields[key] for key in _SESSION_KEYS if fields.get(key)}
        params.update(
            {
                "dse_operationName": self.capabilities.operation,
                "dse_errorPage": "error_page.jsp",
                "dse_nextEventName": self.capabilities.query_event,
                self.capabilities.page_parameter: str(page),
            }
        )
        return self.http.get(
            self.capabilities.request_url,
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
        form_id = self._form_id_for_operation(response.text, self.capabilities.operation, self._search_form_id)
        if not form_id or (self.capabilities.table_id not in response.text and not empty):
            self.logger.warning(
                "SCHEMA_CHANGED: legacy thiếu bảng hoặc form thông báo (HTTP %s)",
                response.status_code,
            )
            if self.session_state is not None:
                # HTTP 200 có thể là trang đăng nhập/xác minh chứ không phải
                # danh sách rỗng; phân loại bằng chứng trước khi báo lỗi.
                raise_terminal(response, 'ETAX_LEGACY', phase='page', authenticated=True)
                raise LegacyEtaxError(
                    "Cổng trả HTTP 200 nhưng thiếu bảng/form thông báo; có thể cổng "
                    "đã đổi cấu trúc hoặc phiên đã hết hạn. Dữ liệu đã tải trước đó "
                    "vẫn được giữ. Hãy thử lại; nếu vẫn lỗi, đăng xuất rồi đăng nhập "
                    "hoặc xem nhật ký kỹ thuật."
                )
            return TbPageResult(http_status=response.status_code, diagnostics=ParseDiagnostics(reasons=["RESULT_FORM_OR_TABLE_MISSING"]))
        self._search_form_id = form_id
        self._search_page_html = response.text
        self._search_page_url = response.url
        parsed = parse_tb_table(response.text, schema=self.capabilities.schema)
        return TbPageResult(
            records=parsed.records,
            total_pages=tb_page_count(response.text, table_id=self.capabilities.table_id),
            http_status=response.status_code,
            diagnostics=parsed.diagnostics,
        )

    def download_tb(self, record: ThongBao) -> bytes | None:
        """Tải PDF thông báo; trả ``None`` khi cổng trả HTML (lỗi/hết phiên)."""
        self.last_download_error = ""
        if not self._search_page_html:
            raise LegacyEtaxError("Chưa có trang kết quả thông báo để tải theo")
        response = self._post_form(
            self._search_page_html,
            self._search_form_id,
            self._search_page_url,
            {
                "dse_operationName": self.capabilities.operation,
                "dse_nextEventName": self.capabilities.download_event,
                "messageId": record.message_id,
                "ma_tbao": record.ma_tbao,
            },
        )
        if response.status_code != 200:
            self.last_download_error = f"Cổng trả HTTP {response.status_code} khi tải PDF; kiểm tra kết nối hoặc phiên đăng nhập."
            return None
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type or not is_tb_pdf(response.content):
            self.last_download_error = "Cổng trả HTML hoặc dữ liệu không phải PDF hoàn chỉnh; có thể phiên hết hạn hoặc cổng đổi định dạng."
            self.logger.error(
                "Thông báo %s không tải được PDF (hết phiên hoặc cổng đổi định dạng)",
                record.message_id,
            )
            return None
        return response.content


__all__ = ["TbPortal", "is_tb_pdf"]
