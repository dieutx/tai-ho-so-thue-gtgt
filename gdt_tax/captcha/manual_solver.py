"""Solver dự phòng: lưu ảnh CAPTCHA ra file rồi hỏi người vận hành nhập tay.

Hữu ích khi cổng đổi kiểu CAPTCHA mà chưa kịp cập nhật OCR: chọn
``GDT_CAPTCHA_SOLVER=manual`` là vẫn chạy được. Không dùng cho tiến trình chạy
nền vì cần bàn phím.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .base import CaptchaSolver

DEFAULT_PROMPT = "Nhập mã CAPTCHA trong ảnh {path}: "


class ManualSolver(CaptchaSolver):
    """Hỏi mã CAPTCHA qua bàn phím."""

    name = "manual"

    def __init__(self, *, prompt: str = DEFAULT_PROMPT, keep_image: bool = False, **options: object) -> None:
        super().__init__(**options)
        self.prompt = prompt
        self.keep_image = keep_image

    def solve(self, image: bytes) -> str:
        with tempfile.NamedTemporaryFile(
            prefix="captcha_", suffix=".png", delete=False
        ) as stream:
            stream.write(image)
            path = Path(stream.name)

        try:
            self.logger.info("Ảnh CAPTCHA: %s", path)
            return input(self.prompt.format(path=path)).strip()
        finally:
            if not self.keep_image:
                path.unlink(missing_ok=True)


__all__ = ["ManualSolver"]
