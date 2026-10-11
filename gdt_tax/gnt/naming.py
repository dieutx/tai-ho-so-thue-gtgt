"""Đặt tên file XML cho một giấy nộp tiền.

Tên gồm số GNT (phần người dùng nhận ra) và ``ctu_id`` (mã duy nhất của cổng),
ngăn bằng ``__`` để lần chạy sau nhận ra file đã tải và bỏ qua::

    000000101234567-01309202639328959__59054902.xml

Số GNT có thể không có hoặc chứa ký tự lạ, nên luôn có ``ctu_id`` làm phần định
danh dự phòng.
"""

from __future__ import annotations

from ..naming import safe_filename_part
from .models import GiayNopTien


def gnt_xml_filename(record: GiayNopTien) -> str:
    """Tên file XML ổn định theo nội dung GNT (số GNT + ``ctu_id``)."""
    parts = []
    if record.so_gnt:
        parts.append(safe_filename_part(record.so_gnt, 60))
    parts.append(safe_filename_part(record.ctu_id or record.so_chung_tu, 60))
    return "__".join(parts) + ".xml"


__all__ = ["gnt_xml_filename"]
