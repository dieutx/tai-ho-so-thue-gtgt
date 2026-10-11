"""Tra cứu giấy nộp tiền và tải XML về (không parse nội dung GNT).

Luồng riêng cho giấy nộp tiền trên trang Thuế điện tử cũ (``thuedientu.gdt.gov.vn``):

* :mod:`gdt_tax.gnt.portal` — tra cứu/tải XML trên etaxnnt;
* :mod:`gdt_tax.gnt.pipeline` — chia đoạn ngày, tải và lưu;
* :mod:`gdt_tax.gnt.storage` — file XML + ``danh_sach_giay_nop_tien.xlsx``;
* :mod:`gdt_tax.gnt.cli` — lệnh ``gdt-gnt`` / ``python -m gdt_tax.gnt``.

Không parse chỉ tiêu bên trong XML giấy nộp tiền; đó là chủ ý của luồng này.
"""

from __future__ import annotations

from .models import GiayNopTien, GntPageResult, GntSummary, gnt_periods
from .pipeline import GntPipeline
from .portal import GntPortal, is_gnt_xml

__all__ = [
    "GiayNopTien",
    "GntPageResult",
    "GntPipeline",
    "GntPortal",
    "GntSummary",
    "gnt_periods",
    "is_gnt_xml",
]
