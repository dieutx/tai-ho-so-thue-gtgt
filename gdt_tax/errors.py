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


class StorageError(GdtError):
    """Không đọc/ghi được file hoặc metadata; giữ nguyên dữ liệu cũ khi lỗi."""


class LegacyEtaxError(GdtError):
    """Không đăng nhập hoặc không tra cứu được trang Thuế điện tử cũ."""


class LegacyPageError(LegacyEtaxError):
    """Trang nghiệp vụ legacy không trả đúng form/màn hình sau khi đã đăng nhập.

    Desktop dùng lỗi này để đóng phiên, đăng nhập lại **một lần** rồi thử lại;
    nếu vẫn lỗi thì báo nguyên văn trang cổng trả về thay vì đoán là hết phiên.
    """
