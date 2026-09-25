"""Bộ nhận dạng CAPTCHA có thể thay thế.

Module này chỉ re-export giao diện và sổ đăng ký. Các backend nặng (``easyocr``)
được nạp muộn qua :func:`create_solver`, nên ``import gdt_tax`` luôn nhẹ.
"""

from __future__ import annotations

from .base import CaptchaSolver, normalize_text
from .images import KIND_LOGIN, KIND_SEARCH, fetch_captcha
from .registry import (
    BUILTIN_SOLVERS,
    available_solvers,
    create_solver,
    register_plugins,
    register_solver,
)

__all__ = [
    "BUILTIN_SOLVERS",
    "CaptchaSolver",
    "KIND_LOGIN",
    "KIND_SEARCH",
    "available_solvers",
    "create_solver",
    "fetch_captcha",
    "normalize_text",
    "register_plugins",
    "register_solver",
]
