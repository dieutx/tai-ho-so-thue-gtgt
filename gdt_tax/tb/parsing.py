"""Đọc bảng kết quả tra cứu thông báo của cơ quan thuế (etaxnnt).

Bảng ``<table id="tbl_tracuu">`` có 10 cột::

    0 STT
    1 Mã thông báo
    2 Tên thông báo
    3 Số thông báo
    4 Ngày gửi thông báo
    5 Cơ quan gửi
    6 Trạng thái            (label ``updateStatus@<messageId>``)
    7 Văn bản giải trình điện tử
    8 Phản hồi kết quả rà soát
    9 Tải thông báo         (``layFileTBao('<messageId>','<ma_tbao>')``)

``messageId`` và ``ma_tbao`` nằm trong lệnh tải của cột 9; đó là hai tham số cổng
dùng để tải PDF nên phải lấy đúng từ đó thay vì từ nội dung hiển thị.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from ..constants import TB_RESULT_TABLE_ID
from ..table_contracts import SCHEMAS, TableParse, parse_table
from .models import ThongBao

TB_MIN_CELLS = 10

_DOWNLOAD_RE = re.compile(
    r"layFileTBao\(\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]", re.I
)


def tb_download_args(row: Tag) -> tuple[str, str]:
    """Cặp ``(messageId, ma_tbao)`` trong lệnh tải của một hàng."""
    match = _DOWNLOAD_RE.search(str(row))
    return (match.group(1), match.group(2)) if match else ("", "")


def tb_record(cells: list[str], row: Tag) -> ThongBao | None:
    """Đọc một hàng thông báo (10 cột) thành :class:`ThongBao`."""
    message_id, ma_tbao = tb_download_args(row)
    if not message_id or len(cells) < TB_MIN_CELLS:
        return None
    row_html = str(row)
    return ThongBao(
        message_id=message_id,
        ma_tbao=ma_tbao,
        ma_thong_bao=cells[1],
        ten_thong_bao=cells[2],
        so_thong_bao=cells[3],
        ngay_gui=cells[4],
        co_quan_gui=cells[5],
        trang_thai=cells[6],
        co_van_ban_giai_trinh="Có" if "gui_vb_gtbs(" in row_html else "",
        co_phan_hoi_ra_soat="Có" if "gui_ph_kq_rs(" in row_html else "",
    )


def parse_tb_records(html: str) -> list[ThongBao]:
    """Đọc mọi thông báo trong bảng kết quả, bỏ trùng theo ``messageId``."""
    return parse_tb_table(html).records


def parse_tb_table(html: str) -> TableParse:
    return parse_table(html, SCHEMAS["TB"], lambda row, cells: tb_record(cells, row), lambda record: record.message_id)


def tb_page_count(html: str) -> int | None:
    """Tổng số trang theo dòng ``Trang 1/ 14``; ``None`` nếu trang không cho biết."""
    text = " ".join(BeautifulSoup(html, "html.parser").stripped_strings)
    match = re.search(r"Trang\s*\d+\s*/\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1))
    return 1 if TB_RESULT_TABLE_ID in html else 0


__all__ = ["TB_MIN_CELLS", "parse_tb_records", "tb_download_args", "tb_page_count", "tb_record"]
