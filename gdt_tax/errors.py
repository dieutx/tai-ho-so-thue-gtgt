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


class PortalVerificationError(GdtError):
    """The portal returned an access verification page instead of app content."""
    code = 'AUTH_ACCESS_VERIFICATION'

    def __init__(self, message):
        super().__init__(self.code + ': ' + message)


class SearchError(GdtError):
    """Không tra cứu được trang kết quả sau nhiều lần thử."""


class SchemaChangedError(SearchError):
    """Result structure is unverified; retrying OCR cannot repair this page."""


class DownloadError(GdtError):
    """Không tải được hồ sơ."""


class AttachmentDownloadError(DownloadError):
    """An attachment request failed without invalidating the primary file."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class StorageError(GdtError):
    """Không đọc/ghi được file hoặc metadata; giữ nguyên dữ liệu cũ khi lỗi."""


class LegacyEtaxError(GdtError):
    """Không đăng nhập hoặc không tra cứu được trang Thuế điện tử cũ."""


class LegacyPageError(LegacyEtaxError):
    """Trang nghiệp vụ legacy không trả đúng form/màn hình sau khi đã đăng nhập.

    Không phải bằng chứng hết phiên; dừng và báo cấu trúc chưa nhận diện.
    """
    code = 'AUTH_SCHEMA_UNKNOWN'

    def __init__(self, message):
        super().__init__(self.code + ': ' + message)


class LegacyPermissionError(LegacyPageError):
    """Tài khoản chưa được phân quyền dùng chức năng legacy.

    Cổng trả HTTP 200 kèm trang "Bạn chưa được phân quyền sử dụng chức năng này!".
    Đây là quyền của tài khoản, không phải cấu trúc trang thay đổi, nên gọi lại
    không sửa được và cũng không nên tính là lượt chạy lỗi.
    """
    code = 'AUTH_FUNCTION_NOT_PERMITTED'

    def __init__(self, message):
        LegacyEtaxError.__init__(self, self.code + ': ' + message)
