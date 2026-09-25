"""Đọc CSRF token từ HTML của cổng Dịch vụ công.

Cổng dùng hai cách đặt token:

* thẻ ``<meta name="csrf-token" content="...">`` (trang đăng nhập)
* ô ẩn ``<input name="_csrf" value="...">`` (trang chi tiết hồ sơ, form ẩn)

Hàm :func:`csrf_token` thử ô ẩn trước rồi mới tới thẻ meta, đúng như luồng
thao tác thật trên trình duyệt.
"""

from __future__ import annotations

from bs4 import BeautifulSoup


def token_from_meta(html: str) -> str:
    """Lấy token từ thẻ ``<meta name="csrf-token">``."""
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("meta", attrs={"name": "csrf-token"})
    return tag.get("content", "") if tag else ""


def token_from_form(html: str) -> str:
    """Lấy token từ ô ẩn ``<input name="_csrf">``."""
    soup = BeautifulSoup(html, "lxml")
    field = soup.find("input", attrs={"name": "_csrf"})
    return field.get("value", "") if field else ""


def csrf_token(html: str, *, prefer_form: bool = True) -> str:
    """Lấy token theo thứ tự ưu tiên, trả về chuỗi rỗng nếu không có."""
    first, second = (
        (token_from_form, token_from_meta)
        if prefer_form
        else (token_from_meta, token_from_form)
    )
    return first(html) or second(html)


__all__ = ["csrf_token", "token_from_form", "token_from_meta"]
