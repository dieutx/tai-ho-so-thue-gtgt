"""Giao diện chung cho mọi bộ nhận dạng CAPTCHA.

Muốn thêm cách nhận dạng mới (OCR khác, dịch vụ trả phí, mô hình nội bộ...)
thì tạo một lớp kế thừa :class:`CaptchaSolver` và đăng ký nó, xem
``docs/ARCHITECTURE.md``.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

#: Ký tự được phép trong mã CAPTCHA của cổng thuế.
_TEXT_DISALLOWED = re.compile(r"[^A-Za-z0-9]+")


def normalize_text(value: str) -> str:
    """Bỏ mọi ký tự không phải chữ-số ASCII khỏi kết quả OCR.

    Dùng regex ASCII thay vì ``str.isalnum()`` vì ``isalnum()`` coi cả chữ có
    dấu tiếng Việt là hợp lệ, trong khi CAPTCHA chỉ có ``A-Z``, ``a-z`` và ``0-9``.
    """
    return _TEXT_DISALLOWED.sub("", value or "")


class CaptchaSolver(ABC):
    """Nhận ảnh CAPTCHA (bytes) và trả về chuỗi mã đã đọc được."""

    #: Tên dùng cho ``GDT_CAPTCHA_SOLVER``.
    name: str = "base"

    def __init__(self, **options: object) -> None:
        self.options = options
        self.logger = logging.getLogger(f"gdt_tax.captcha.{self.name}")

    @abstractmethod
    def solve(self, image: bytes) -> str:
        """Đọc mã trong ảnh; trả về chuỗi rỗng nếu không đọc được."""

    def close(self) -> None:
        """Giải phóng tài nguyên (mô hình, kết nối...). Mặc định không làm gì."""
        return None

    def __repr__(self) -> str:  # pragma: no cover - chỉ để log dễ đọc
        return f"{type(self).__name__}(name={self.name!r})"


__all__ = ["CaptchaSolver", "normalize_text"]
