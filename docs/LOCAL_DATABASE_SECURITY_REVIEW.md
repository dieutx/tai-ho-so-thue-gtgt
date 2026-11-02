# Review phạm vi nâng cấp kho local

- Không đọc `.env` hoặc lấy password thuế để chạy test. Pilot nhập trực tiếp dialog/vault hiện hữu; không thêm secret vào SQLite/settings/report.
- Tất cả SQL dùng bound parameters; toán tử ngày chỉ từ hằng số. RecordKey/account/source/kind phải khớp; mơ hồ vào quarantine. Legacy unowned không được nhận theo tên folder.
- Đường dẫn artifact resolve và phải nằm trong workspace; SQLite symlink bị từ chối. File tải giữ atomic save/evidence của core; không đổi policy verify thành chỉ kiểm đuôi file.
- Mỗi operation tự mở/đóng connection; BEGIN IMMEDIATE bảo vệ upsert; busy timeout 5s; FK ON; index account/mode/date; không bật WAL trên thư mục cloud/share. Không dùng connection xuyên Qt worker/UI.
- Discovery commit trước download; commit file xong checkpoint; cancel/error không DELETE. DB backup trước import/schema; integrity và inspector read-only.
- Không cất raw HTTP trong metrics; chỉ đếm category/status/bytes/latency. Chưa thêm service telemetry hoặc gửi dữ liệu thuế cho bên thứ ba.
- Bản build không nhúng DB thuế hoặc fixture; audit bundle và frozen smoke phải PASS trước release. File kế hoạch, docs và tests chỉ chứa dữ liệu tổng hợp.
- Giới hạn: SQLite không mã hóa metadata; người có quyền đọc thư mục Windows có thể xem hồ sơ. Xem local không phải portal authentication. Không có UI sửa quarantine. Chưa chứng minh multi-machine/cloud-sync an toàn hoặc concurrent portal sessions.
