"""Tải ảnh CAPTCHA từ cổng Dịch vụ công.

Cổng dùng hai endpoint khác nhau cho trang đăng nhập và trang tra cứu, và chỉ
trả ảnh khi phiên đã có (cookie hợp lệ).
"""

from __future__ import annotations

import logging
import time

from ..constants import LANDING, LOGIN_CAPTCHA, LOGIN_PAGE, SEARCH_CAPTCHA
from ..headers import DEFAULT_PROFILE, build_image_headers
from ..http import HttpClient

LOGGER_NAME = "gdt_tax.captcha"
KIND_LOGIN = "login"
KIND_SEARCH = "search"

MIN_IMAGE_BYTES = 500


def fetch_captcha(
    http: HttpClient,
    kind: str = KIND_SEARCH,
    *,
    logger: logging.Logger | None = None,
    profile: str = DEFAULT_PROFILE,
) -> bytes | None:
    """Trả về bytes ảnh CAPTCHA, hoặc ``None`` nếu cổng không trả ảnh hợp lệ."""
    logger = logger or logging.getLogger(LOGGER_NAME)
    is_login = kind == KIND_LOGIN
    path = LOGIN_CAPTCHA if is_login else SEARCH_CAPTCHA
    referer = http.url(LOGIN_PAGE if is_login else LANDING)

    response = http.get(
        path,
        params={"_": int(time.time() * 1000)},
        headers=build_image_headers(profile=profile, headers={"Referer": referer}),
    )
    content_type = response.headers.get("content-type", "").lower()
    if (
        response.status_code != 200
        or "image" not in content_type
        or len(response.content) < MIN_IMAGE_BYTES
    ):
        logger.error(
            "Lỗi CAPTCHA: HTTP=%s, content-type=%s, %s bytes",
            response.status_code,
            content_type or "?",
            len(response.content),
        )
        return None
    return response.content


__all__ = ["KIND_LOGIN", "KIND_SEARCH", "fetch_captcha"]
