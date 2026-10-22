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


def issue_hint(message) -> str:
    """Gợi ý xử lý theo nhóm lỗi; không thay đổi nội dung lỗi gốc."""
    text = str(message or '').casefold()
    if any(marker in text for marker in ('hết hạn', 'phiên đăng nhập', 'đăng nhập lại')):
        return 'Phiên đăng nhập đã hết hạn: đăng nhập lại rồi thử lại tệp này.'
    if any(marker in text for marker in ('429', 'giới hạn tần suất', 'quá nhiều yêu cầu')):
        return 'Cổng đang giới hạn tần suất: chờ vài phút rồi bấm Thử lại tệp lỗi.'
    if 'captcha' in text:
        return 'CAPTCHA chưa đúng: thử lại; nếu tự động thất bại, nhập tay khi được hỏi.'
    if any(marker in text for marker in ('mạng', 'network', 'kết nối', 'max retries', 'timeout')):
        return 'Kiểm tra kết nối mạng/proxy rồi thử lại; tệp đã tải hợp lệ được giữ nguyên.'
    if any(marker in text for marker in ('quyền', 'permission', 'bị khóa', 'dung lượng', 'disk', 'enospc')):
        return 'Kiểm tra quyền ghi/dung lượng, đóng Excel/OneDrive rồi thử lại; không xóa tệp hợp lệ.'
    if any(marker in text for marker in ('không phải zip', 'không phải xml', 'không phải pdf',
                                         'định dạng', 'không hợp lệ', 'giải mã')):
        return 'Tệp cổng trả về không hợp lệ: thử lại; nếu lặp lại, mở Nhật ký kỹ thuật để kiểm tra.'
    if 'không đúng loại hồ sơ' in text:
        return 'Tệp ZIP hợp lệ nhưng không đúng loại tờ khai/thông báo; kiểm tra lại loại hồ sơ.'
    if 'không còn trong kết quả' in text:
        return 'Hồ sơ không còn trong kết quả tra cứu: tra cứu lại đúng kỳ rồi tải lại.'
    return 'Thử lại tệp này; nếu vẫn lỗi, mở Nhật ký kỹ thuật để xem chi tiết.'


__all__ = ['issue_hint', 'storage_message']

