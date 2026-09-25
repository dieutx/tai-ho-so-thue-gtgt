"""Cây ngoại lệ của công cụ.

Mọi lỗi có thể dự đoán đều kế thừa :class:`GdtError` để ``cli`` bắt một chỗ và
trả về mã thoát phù hợp.
"""

from __future__ import annotations


class GdtError(Exception):
    """Lỗi chung của công cụ."""


class ConfigError(GdtError):
    """Cấu hình thiếu hoặc sai (biến môi trường, file .env, tham số dòng lệnh)."""


class LoginError(GdtError):
    """Không đăng nhập được vào Cổng Dịch vụ công."""


class NetworkError(GdtError):
    """Không gửi được request (mạng, proxy, hoặc cổng chặn kết nối).

    ``HttpClient`` đổi mọi lỗi của ``requests`` thành lỗi này để chương trình báo
    bằng một dòng dễ hiểu thay vì traceback, và để thông báo đã được che mật khẩu
    proxy.
    """


class CaptchaError(GdtError):
    """Không nạp hoặc không dùng được bộ nhận dạng CAPTCHA."""


class SearchError(GdtError):
    """Không tra cứu được trang kết quả sau nhiều lần thử."""


class DownloadError(GdtError):
    """Không tải được hồ sơ."""
