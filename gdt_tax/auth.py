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
from .constants import LANDING, LOGIN_ENDPOINT, LOGIN_PAGE, ORIGIN
from .csrf import token_from_meta
from .errors import LoginError
from .headers import DEFAULT_PROFILE, build_page_headers, build_xhr_headers
from .http import HttpClient
from .run_hooks import RunHooks

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

    hooks = getattr(http, "hooks", RunHooks())
    for attempt in range(1, settings.login_attempts + 1):
        if hooks.budget is not None:
            hooks.budget.authenticate()
        logger.info("ĐĂNG NHẬP %s/%s", attempt, settings.login_attempts)
        page = http.get(
            LOGIN_PAGE,
            headers=build_page_headers(
                profile=settings.header_profile,
                site="none",
                headers={"Referer": f"{ORIGIN}/"},
            ),
        )
        if page.status_code != 200:
            logger.warning("Không mở được trang đăng nhập: HTTP %s", page.status_code)
            hooks.pause(PAUSE_BEFORE_RETRY, time.sleep)
            continue

        csrf = token_from_meta(page.text)
        image = fetch_captcha(
            http, KIND_LOGIN, logger=logger, profile=settings.header_profile
        )
        captcha_text = captcha.solve(image) if image else ""
        if not csrf or not captcha_text:
            logger.warning(
                "Bỏ lần thử này: %s",
                "không lấy được CSRF token từ trang đăng nhập"
                if not csrf
                else "bộ nhận dạng CAPTCHA không đọc được mã",
            )
            hooks.pause(PAUSE_BEFORE_RETRY, time.sleep)
            continue

        response = http.post(
            LOGIN_ENDPOINT,
            data={
                "tenDN": settings.username,
                "matKhau": payload,
                "doiTuong": "DN",
                "captcha": captcha_text,
            },
            headers=build_xhr_headers(
                profile=settings.header_profile,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Origin": ORIGIN,
                    "Referer": http.url(LOGIN_PAGE),
                    "X-Requested-With": "XMLHttpRequest",
                    "X-XSRF-TOKEN": csrf,
                },
            ),
        )
        logger.info("LOGIN: HTTP=%s", response.status_code)

        try:
            if str(response.json().get("status")) == "200":
                accepted = getattr(captcha, "accepted", None)
                if callable(accepted):
                    accepted()
                logger.info("ĐĂNG NHẬP THÀNH CÔNG")
                return True
        except (ValueError, AttributeError):
            pass
        rejected = getattr(captcha, "rejected", None)
        if callable(rejected):
            rejected()
        hooks.pause(PAUSE_AFTER_FAILED_LOGIN, time.sleep)

    return False


def open_landing(
    http: HttpClient,
    logger: logging.Logger | None = None,
    *,
    profile: str = DEFAULT_PROFILE,
) -> str:
    """Mở trang hồ sơ và trả về HTML (nguồn của CSRF token cho luồng ETAX)."""
    logger = logger or logging.getLogger(LOGGER_NAME)
    response = http.get(LANDING, headers=build_page_headers(profile=profile))
    if response.status_code != 200:
        raise LoginError(f"Không mở được trang hồ sơ: HTTP {response.status_code}")
    logger.debug("Đã mở trang hồ sơ (%s bytes)", len(response.content))
    return response.text


__all__ = ["login", "open_landing"]
