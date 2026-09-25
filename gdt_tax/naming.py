"""Đặt tên file ZIP theo thông tin tờ khai.

Tên file được tạo từ 4 phần, ngăn bằng ``__`` để vẫn đọc được khi liệt kê thư mục::

    <mã hồ sơ>__<kỳ tính thuế>__<loại tờ khai>__<tên tờ khai>.zip

Ví dụ::

    11320250292469209__12-2024__Chinh-thuc__TO-KHAI-THUE-GIA-TRI-GIA-TANG.zip
"""

from __future__ import annotations

import re
import unicodedata

from .models import CaseRecord

UNKNOWN = "khong-ro"
_SEPARATOR = "__"

# ``đ`` không tách được thành ``d`` bằng NFKD nên phải đổi trước khi bỏ dấu.
_SPECIAL_LETTERS = str.maketrans({"đ": "d", "Đ": "D", "ð": "d", "Ð": "D"})


def safe_filename_part(value: str, maximum: int = 70) -> str:
    """Chuyển text tiếng Việt thành phần tên file an toàn trên mọi hệ điều hành."""
    text = (value or "").translate(_SPECIAL_LETTERS)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return text[:maximum] or UNKNOWN


def zip_filename(record: CaseRecord) -> str:
    """Tên file ZIP gợi nhớ đủ thông tin: mã hồ sơ, kỳ, loại và tên tờ khai."""
    parts = (
        safe_filename_part(record.ma_ho_so, 50),
        safe_filename_part(record.ky_tinh_thue, 20),
        safe_filename_part(record.loai_to_khai, 30),
        safe_filename_part(record.to_khai, 70),
    )
    return _SEPARATOR.join(parts) + ".zip"


__all__ = ["UNKNOWN", "safe_filename_part", "zip_filename"]
