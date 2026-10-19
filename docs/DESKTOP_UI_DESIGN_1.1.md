# Compact Desktop 1.1

Qt Widgets, Segoe UI 12 logical px, nền sáng #F3F6FA, accent #2563EB.
Nút tài khoản xanh ngọc, tác vụ chính xanh lam, dừng hồng, tệp/nhật ký tím.
Có nhãn chữ cho trạng thái; Settings cho phép chọn theme tối. Không có
QScrollArea bao cửa sổ chính.

```text
Hồ Sơ Thuế [v1.1.0]     MST / phiên ETAX  [Đăng nhập] [Settings]
[Tờ khai] [Giấy nộp tiền] [Thông báo thuế] [Phân tích XML]
Từ / Đến / Nơi lưu / tùy chọn (offline: Nguồn + Nơi xuất)
Tìm trong kết quả                         Counters thực
QTableView co giãn, cuộn nội bộ, empty state hướng dẫn
Tra cứu / Tra cứu & tải / Dừng    Trạng thái  [Tệp & nhật ký]
```

- Một dialog tài khoản duy nhất, giữ nút để hiện mật khẩu tạm thời. Header
  hiển thị phiên chung; chuyển tab không gọi mạng, không xóa kết quả.
- Ngày và nơi lưu chung cho online; ngày mặc định là toàn bộ tháng trước.
  Offline không hiển thị ngày/CAPTCHA, không cần tài khoản hoặc mạng.
- Bảng luôn hiện, mỗi tab giữ filter, sort, vị trí cuộn và trạng thái riêng.
  Nguồn/nơi xuất offline tách hàng khi hẹp; đường dẫn elide giữa, tooltip đủ.
- Dưới 850 px hoặc thấp hơn 560 logical px: rút nhãn và gom thao tác phụ vào
  menu. Dưới 600 px dùng combo điều hướng. Không chuyển qua subview làm mất bảng.
- Cột bị ẩn ở màn hình hẹp vẫn có trong chi tiết/tooltip; lọc cục bộ không gọi mạng.
- QScreen.availableGeometry tính cả frame/taskbar và tọa độ màn hình âm.
  Ma trận kiểm tra năm độ phân giải × ba mức scale; trừ 40 physical px taskbar,
  rồi kiểm tra frame và các widget thực tế. Đây là mô phỏng workarea, không đổi DPI OS.
- Settings, chi tiết phiên bản/cập nhật và nhật ký có thể cuộn trong dialog.
  Worker QThread thực hiện HTTP/OCR/I/O. Dừng qua token, không kill thread.
- DVC mặc định bật theo yêu cầu mới; tắt vẫn cảnh báo phạm vi thiếu.
  Phiên bản cho biết nội dung mới và cách kiểm tra bản phát hành, không tự cập nhật.

Ảnh thật từ EXE và kết quả kiểm tra nằm trong DESKTOP_ACCEPTANCE.md.
Ảnh minh chứng chỉ dùng trạng thái trống/fixture, không chứa hồ sơ thuế thật.
