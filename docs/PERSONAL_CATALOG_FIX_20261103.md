# Bảng cá nhân trống sau tải — bản sửa 2.1.3

Code: `5aadcbeef0dda082a670ba12a405b978788d5ce1`.

## Nguyên nhân và dữ liệu hiện có

Worker đã ghi đúng 24 hồ sơ vào kho `ca-nhan`, nhưng đường đọc danh mục vẫn
dùng thư mục doanh nghiệp. Ba điểm bỏ sót loại tài khoản: cấu hình nạp kho sau
đăng nhập, refresh bảng theo kỳ và hàm liệt kê thư mục kho. Vì vậy tác vụ online
có kết quả mà bảng và bộ đếm local vẫn bằng 0. Kiểm chứng 2.1.2 trước đó đã
chạy Worker và tải/reuse, nhưng thiếu bước đối chiếu bảng GUI với kho cá nhân.

Đọc database thực tế trên máy: 24 hồ sơ, gồm 17 đã tải và 7 đang báo lỗi
`INVALID_XML` từ lượt tải trước. Bản sửa đọc lại dữ liệu ở vị trí hiện có,
không cần chuyển kho hay tải lại các tệp đã có. Các hồ sơ tải lỗi vẫn hiện
với trạng thái lỗi, không bị đổi thành chưa tải khi refresh danh sách.

## Kiểm chứng

- Bốn kiểm thử tái hiện lỗi thất bại trên 2.1.2, đạt sau sửa: hoàn tất tác vụ
  với 24 hồ sơ, đổi kỳ, nạp kho sau đăng nhập và đọc cả thư mục chính/tai-moi.
- Thêm kiểm thử giữ trạng thái lỗi khi đọc kho.
- GUI từ source đọc chính database hiện có: found=24, downloaded=17,
  failed=7, pending=0; chặn mọi request mạng trong lượt kiểm tra này.
- Bộ desktop: 973 tests, 6 skip OCR tùy chọn; ruff và mypy đạt.
- Smoke mới gọi trực tiếp `MainWindow.on_completed` trong source và EXE:
  24 hồ sơ cá nhân phải hiện đủ; bản ghi doanh nghiệp cùng tên đăng nhập
  không được lọt vào bảng; cấu hình nạp kho phải giữ `account_type=CN`.

Build chạy trong worktree riêng vì EXE 2.1.2 đang mở. Artifact bàn giao nằm
ở `dist/2.1.3/`, không ghi đè file đang chạy. Kết quả bundle/smoke/provenance
và checksum sẽ được chốt sau khi build hoàn tất.
