"""Giai đoạn xác thực: đăng nhập và mở trang hồ sơ.

Cổng đăng nhập bằng ``POST /tchs/loginLDAP`` với mật khẩu mã hoá Base64, kèm
CAPTCHA và header ``X-XSRF-TOKEN`` lấy từ thẻ meta của trang đăng nhập. Vì
CAPTCHA có thể đọc sai, hàm :func:`login` thử lại nhiều lần theo cấu hình.
"""

from __future__ import annotations

import base64
import logging
import time

from .captcha import KIND_LOGIN, CaptchaSolver, fetch_captcha
from .constants import (
    DEFAULT_HEADERS,
    LANDING,
    LOGIN_ENDPOINT,
    LOGIN_PAGE,
    ORIGIN,
)
from .csrf import token_from_meta
from .errors import LoginError
from .http import HttpClient

LOGGER_NAME = "gdt_tax.auth"
PAUSE_BEFORE_RETRY = 3.0
PAUSE_AFTER_FAILED_LOGIN = 4.0


def login(
    http: HttpClient,
    captcha: CaptchaSolver,
    settings,
    logger: logging.Logger | None = None,
) -> bool:
    """Thử đăng nhập; trả ``True`` khi cổng xác nhận ``status = 200``."""
    logger = logger or logging.getLogger(LOGGER_NAME)
    payload = base64.b64encode(settings.password.encode("utf-8")).decode("ascii")

    for attempt in range(1, settings.login_attempts + 1):
        logger.info("ĐĂNG NHẬP %s/%s", attempt, settings.login_attempts)
        page = http.get(LOGIN_PAGE, headers={**DEFAULT_HEADERS, "Referer": f"{ORIGIN}/"})
        if page.status_code != 200:
            logger.warning("Không mở được trang đăng nhập: HTTP %s", page.status_code)
            time.sleep(PAUSE_BEFORE_RETRY)
            continue

        csrf = token_from_meta(page.text)
        image = fetch_captcha(http, KIND_LOGIN, logger=logger)
        captcha_text = captcha.solve(image) if image else ""
        if not csrf or not captcha_text:
            time.sleep(PAUSE_BEFORE_RETRY)
            continue

        response = http.post(
            LOGIN_ENDPOINT,
            data={
                "tenDN": settings.username,
                "matKhau": payload,
                "doiTuong": "DN",
                "captcha": captcha_text,
            },
            headers={
                **DEFAULT_HEADERS,
                "Accept": "*/*",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": ORIGIN,
                "Referer": http.url(LOGIN_PAGE),
                "X-Requested-With": "XMLHttpRequest",
                "X-XSRF-TOKEN": csrf,
            },
        )
        logger.info("LOGIN: HTTP=%s %s", response.status_code, response.text[:200])

        try:
            if str(response.json().get("status")) == "200":
                logger.info("ĐĂNG NHẬP THÀNH CÔNG")
                return True
        except (ValueError, AttributeError):
            pass
        time.sleep(PAUSE_AFTER_FAILED_LOGIN)

    return False


def open_landing(http: HttpClient, logger: logging.Logger | None = None) -> str:
    """Mở trang hồ sơ và trả về HTML (nguồn của CSRF token cho luồng ETAX)."""
    logger = logger or logging.getLogger(LOGGER_NAME)
    response = http.get(LANDING, headers=DEFAULT_HEADERS)
    if response.status_code != 200:
        raise LoginError(f"Không mở được trang hồ sơ: HTTP {response.status_code}")
    logger.debug("Đã mở trang hồ sơ (%s bytes)", len(response.content))
    return response.text


__all__ = ["login", "open_landing"]
