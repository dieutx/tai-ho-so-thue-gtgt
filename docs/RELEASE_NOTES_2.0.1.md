# Tải Hồ Sơ Thuế 2.0.1 — Windows x64

Bản phát hành công khai kế tiếp sau 2.0.0; gộp các bản nội bộ 2.0.1–2.0.4 và bộ UX mới.

## Điểm mới

- **Phản hồi CQT** dạng bảng con trong tab Tờ khai: xem từng phản hồi, XML,
  trạng thái chấp nhận/từ chối và mở tệp ngay tại chỗ.
- **XML Viewer** hai chế độ: nội dung dễ đọc và XML gốc; hỗ trợ sao chép/lưu.
- **Thông báo thuế** là tab độc lập, có bộ lọc và thao tác xem/tải tệp.
- **Xuất hồ sơ ZIP** có manifest, kèm phản hồi của đúng lần nộp.
- **Đối soát và xuất báo cáo** CSV/XLSX theo các dòng đang lọc.
- **Tự kiểm tra bản mới khi mở app:** hiện banner ngay trên cửa sổ với nút
  **Tải ngay**/**Để sau** và nháy taskbar nếu app không được focus; không cần
  bấm kiểm tra. Chỉ gọi API công khai GitLab, không gửi thông tin tài khoản thuế.
- Sửa `RECORD_HANDLER_OR_ID_MISSING`: bỏ qua hàng không phải dữ liệu, không
  còn báo lỗi giả; vẫn cảnh báo khi handler có nhưng ID lệch.
- Nhận đúng ZIP thông báo `04/SS-HĐĐT` (XML `<TBao>`), không còn báo nhầm
  "không phải ZIP"; tờ khai vẫn bắt buộc XML declaration.
- Tối ưu HTTP 429: chờ **2s → 4s → 8s** thay vì 15 giây/lần (tôn trọng
  `Retry-After` nếu cổng gửi); dùng lại trang chi tiết/CSRF để bớt request.
- Giữ lưu mật khẩu trong Windows Credential Manager, retry thông báo và
  định danh tài khoản/hồ sơ của 2.0.4.

## Kiểm thử

- **861 tests OK (6 skip)**, ruff và mypy pass.
- Tài khoản thật: **4/4** hồ sơ `04/SS-HĐĐT` tải và lưu thành công.
- Tài khoản thật: **12/12** thông báo của một hồ sơ tải trong **14,23 giây**,
  không lỗi.
- Audit bundle, frozen offline smoke, GUI và 18/18 UI/DPI pass.

## Tải và kiểm tra

- Tải bản mới nhất:
  https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/releases/permalink/latest/downloads/TaiHoSoThue-Windows.exe
- Danh sách phát hành: https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/releases
- Mã SHA-256 của EXE nằm trong `SHA256SUMS.txt` đính kèm release.

## Ghi chú

- Yêu cầu Windows x64; chạy bằng một file EXE, không cần cài Python/Excel.
- Bản build chưa ký Authenticode; Windows SmartScreen có thể hiện cảnh báo.
- Dữ liệu đã tải vẫn được giữ và dùng lại; không xóa thư mục hồ sơ khi nâng cấp.
- Không hỗ trợ nhiều MST đồng thời; chuyển tài khoản tuần tự, dữ liệu tách theo tài khoản.
