"""Đọc bảng kết quả tra cứu giấy nộp tiền trên trang Thuế điện tử cũ.

Trang trả bảng ``<table id="data_content_onday">`` với 20 cột::

    0  STT
    1  Số tham chiếu/ Mã giao dịch
    2  Mã giao dịch DS chi tiết
    3  Lần nộp
    4  Số giấy nộp tiền          (link ``chiTietCT(<ctuId>)``)
    5  Số tiền
    6  Loại tiền
    7  Trạng thái
    8  Số chứng từ
    9  Ngày lập GNT
    10 Ngày gửi GNT
    11 Ngày nộp thuế
    12 Có DS chi tiết TNCN        (link ``uploadBke(...)``)
    13 Có DS chi tiết TMĐT        (link ``uploadBkeTMDT(...)``)
    14 Ngày nộp DS chi tiết
    15 Hình thức nộp
    16 Ngân hàng
    17 Tài khoản ngân hàng
    18 #                         (link ``downloadGNT(<ctuId>)``)
    19 Thông báo

``ctuId`` lấy từ ``downloadGNT(<id>)`` (thiếu thì lấy từ ``chiTietCT(<id>)``) vì
đó là tham số cổng dùng để tải XML.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from ..constants import GNT_RESULT_TABLE_ID
from ..html_text import visible_text
from ..table_contracts import SCHEMAS, TableParse, parse_table
from .models import GiayNopTien

GNT_MIN_CELLS = 20

_CTU_RE = re.compile(r"(?:downloadGNT|chiTietCT)\(\s*['\"]?(\d+)", re.I)


def gnt_ctu_id(row: Tag) -> str:
    """Mã nội bộ ``ctuId`` của một hàng, dùng cho lệnh tải XML."""
    ids = set(_CTU_RE.findall(str(row)))
    return next(iter(ids)) if len(ids) == 1 else ""


def gnt_record(cells: list[str], row: Tag) -> GiayNopTien | None:
    """Đọc một hàng bảng GNT (20 cột) thành :class:`GiayNopTien`."""
    ctu_id = gnt_ctu_id(row)
    if not ctu_id or len(cells) < GNT_MIN_CELLS:
        return None
    row_html = str(row)
    return GiayNopTien(
        ctu_id=ctu_id,
        so_tham_chieu=cells[1],
        ma_giao_dich_chi_tiet=cells[2],
        lan_nop=cells[3],
        so_gnt=cells[4],
        so_tien=cells[5],
        loai_tien=cells[6],
        trang_thai=cells[7],
        so_chung_tu=cells[8],
        ngay_lap=cells[9],
        ngay_gui=cells[10],
        ngay_nop=cells[11],
        co_ds_chi_tiet_tncn="Có" if "uploadBke(" in row_html else "",
        co_ds_chi_tiet_tmdt="Có" if "uploadBkeTMDT(" in row_html else "",
        ngay_nop_ds_chi_tiet=cells[14],
        hinh_thuc_nop=cells[15],
        ngan_hang=cells[16],
        tai_khoan=cells[17],
        thong_bao=cells[19],
    )


def parse_gnt_records(html: str) -> list[GiayNopTien]:
    """Đọc mọi giấy nộp tiền trong bảng kết quả, bỏ trùng theo ``ctu_id``."""
    return parse_gnt_table(html).records


def parse_gnt_table(html: str, *, schema=None) -> TableParse:
    return parse_table(html, schema or SCHEMAS["GNT"], lambda row, cells: gnt_record(cells, row), lambda record: record.ctu_id)


def gnt_page_count(html: str, *, table_id: str = GNT_RESULT_TABLE_ID) -> int | None:
    """Tổng số trang theo dòng ``Trang 1/ 2``; ``None`` nếu trang không cho biết."""
    text = visible_text(BeautifulSoup(html, 'html.parser'))
    match = re.search(r"Trang\s*\d+\s*/\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1))
    return 1 if table_id in html else 0


__all__ = ["GNT_MIN_CELLS", "gnt_ctu_id", "gnt_page_count", "gnt_record", "parse_gnt_records"]
