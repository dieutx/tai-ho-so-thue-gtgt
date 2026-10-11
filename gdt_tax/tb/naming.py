"""Đặt tên file PDF cho một thông báo của cơ quan thuế.

Tên gồm số thông báo (phần người dùng nhận ra) và ``messageId`` (mã duy nhất của
cổng), ngăn bằng ``__`` để lần chạy sau nhận ra file đã tải và bỏ qua::

    25799-TB-TCS1-KDT__11200000290415416.pdf
"""

from __future__ import annotations

from ..naming import safe_filename_part
from .models import ThongBao


def tb_pdf_filename(record: ThongBao) -> str:
    """Tên file PDF ổn định theo nội dung thông báo (số thông báo + ``messageId``)."""
    parts = []
    if record.so_thong_bao:
        parts.append(safe_filename_part(record.so_thong_bao, 60))
    parts.append(record.message_id or safe_filename_part(record.ma_thong_bao, 40))
    return "__".join(parts) + ".pdf"


__all__ = ["tb_pdf_filename"]
