"""Tra cứu và tải thông báo của cơ quan thuế (PDF) trên trang Thuế điện tử cũ.

* :mod:`gdt_tax.tb.portal` — tra cứu/tải PDF trên etaxnnt;
* :mod:`gdt_tax.tb.pipeline` — chia đoạn ngày, tải và lưu;
* :mod:`gdt_tax.tb.storage` — file PDF + ``danh_sach_thong_bao.xlsx``;
* :mod:`gdt_tax.tb.cli` — lệnh ``gdt-tb`` / ``python -m gdt_tax.tb``.

Không parse nội dung PDF; đó là chủ ý của luồng này.
"""

from __future__ import annotations

from .models import TbPageResult, TbSummary, ThongBao, tb_periods
from .pipeline import TbPipeline
from .portal import TbPortal, is_tb_pdf

__all__ = [
    "TbPageResult",
    "TbPipeline",
    "TbPortal",
    "TbSummary",
    "ThongBao",
    "is_tb_pdf",
    "tb_periods",
]
