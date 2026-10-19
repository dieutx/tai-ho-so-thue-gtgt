"""Actionable Windows storage messages; technical exceptions stay in the log."""
import errno


def storage_message(error, prefix='Không lưu được tệp'):
    current = error
    codes = []
    while current is not None and len(codes) < 8:
        codes.append((getattr(current, 'errno', None), getattr(current, 'winerror', None)))
        current = current.__cause__
    if any(number == errno.ENOSPC or windows == 112 for number, windows in codes):
        reason = 'ổ đĩa đã hết dung lượng. Giải phóng dung lượng hoặc chọn nơi lưu khác'
    elif any(windows in {32, 33} for _, windows in codes):
        reason = 'tệp đang bị khóa/mở bởi ứng dụng khác. Đóng Excel hoặc ứng dụng đang mở tệp rồi thử lại'
    elif any(number in {errno.EACCES, errno.EPERM} or windows == 5 for number, windows in codes):
        reason = 'không có quyền ghi hoặc tệp đang bị khóa. Chọn thư mục có quyền ghi; đóng Excel/tạm dừng OneDrive nếu đang sử dụng'
    elif any(number == errno.EINVAL or windows == 123 for number, windows in codes):
        reason = 'đường dẫn hoặc tên tệp không hợp lệ. Chọn lại nơi lưu và kiểm tra tên tệp'
    else:
        reason = 'kiểm tra quyền ghi, dung lượng, đóng Excel hoặc tạm dừng đồng bộ OneDrive rồi thử lại'
    return prefix + ': ' + reason + '. Tệp hồ sơ đã hoàn tất được giữ nguyên.'
