"""Solver CAPTCHA qua một dịch vụ HTTP bên ngoài (tùy chọn).

Cố ý **không** gắn cứng nhà cung cấp nào: chỉ cần một endpoint nhận ảnh và trả
mã, cấu hình qua ``GDT_CAPTCHA_OPTIONS``. Nhờ đó khi cổng đổi loại CAPTCHA, chỉ
cần đổi cấu hình hoặc viết solver mới, không phải sửa luồng tải hồ sơ.

Ví dụ::

    GDT_CAPTCHA_SOLVER=remote
    GDT_CAPTCHA_OPTIONS={"url": "https://example.com/solve", "api_key": "...", "result_field": "data.text"}

``result_field`` hỗ trợ đường dẫn lồng nhau kiểu ``data.text``; để trống thì
dùng chính phản hồi nếu đó là chuỗi.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import CaptchaError
from .base import CaptchaSolver

DEFAULT_IMAGE_FIELD = "image"


class RemoteHttpSolver(CaptchaSolver):
    """Gửi ảnh CAPTCHA tới một endpoint HTTP và đọc mã trả về."""

    name = "remote"

    def __init__(
        self,
        *,
        url: str = "",
        api_key: str = "",
        method: str = "POST",
        timeout: int = 30,
        image_field: str = DEFAULT_IMAGE_FIELD,
        api_key_header: str = "Authorization",
        result_field: str = "",
        extra_fields: Mapping[str, str] | None = None,
        **options: object,
    ) -> None:
        super().__init__(**options)
        if not url:
            raise CaptchaError(
                "Solver 'remote' cần 'url'. Ví dụ GDT_CAPTCHA_OPTIONS="
                '{"url": "https://example.com/solve"}'
            )
        self.url = url
        self.api_key = api_key
        self.method = method.upper()
        self.timeout = timeout
        self.image_field = image_field
        self.api_key_header = api_key_header
        self.result_field = result_field
        self.extra_fields = dict(extra_fields or {})

    def solve(self, image: bytes) -> str:
        import requests

        headers = {self.api_key_header: self.api_key} if self.api_key else {}
        files = {self.image_field: ("captcha.png", image, "image/png")}

        response = requests.request(
            self.method,
            self.url,
            headers=headers,
            files=files,
            data=dict(self.extra_fields),
            timeout=self.timeout,
        )
        if response.status_code != 200:
            self.logger.error("Dịch vụ CAPTCHA trả HTTP %s: %s", response.status_code, response.text[:200])
            return ""

        try:
            payload: Any = response.json()
        except ValueError:
            return response.text.strip()

        return str(self._extract(payload)).strip()

    def _extract(self, payload: Any) -> Any:
        if not self.result_field:
            return payload if isinstance(payload, str) else ""
        current = payload
        for key in self.result_field.split("."):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                self.logger.error("Phản hồi dịch vụ CAPTCHA thiếu trường %r", self.result_field)
                return ""
        return current


__all__ = ["RemoteHttpSolver"]
