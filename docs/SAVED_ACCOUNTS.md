# Danh sách công ty và mật khẩu đã lưu (2.0.3)

Bấm MST trên thanh đầu để mở danh sách công ty đã lưu. Chọn công ty mở hộp
đăng nhập, tự điền MST/mật khẩu; bấm Đăng nhập để kết nối. Cũng có thể chọn
MST trong danh sách ở hộp đăng nhập hoặc gõ tài khoản mới. Đổi MST xóa mật khẩu
đang hiển thị trước khi đọc mật khẩu của đúng công ty. Đổi tài khoản vẫn dừng
tác vụ hiện tại an toàn, xóa phiên cũ và xóa bảng kết quả của tài khoản trước.

Tùy chọn “Lưu mật khẩu trên máy này” mặc định bật, chỉ ghi khi đăng nhập thành
công. Có thể bỏ chọn để chỉ giữ trong phiên. Đăng xuất không xóa danh sách đã
lưu; nút “Quên tài khoản đã lưu” xóa đúng tài khoản đang chọn khỏi kho Windows.
Nếu kho Windows không truy cập được, vẫn nhập mật khẩu để đăng nhập phiên.

Kho dùng API WinCred (`CRED_TYPE_GENERIC`, `CRED_PERSIST_LOCAL_MACHINE`), với
namespace riêng `TaiHoSoThue/ETAX/v1/` và khóa SHA-256 của tên tài khoản. Chỉ
liệt kê namespace này; không đọc hay sửa credential của ứng dụng khác. Không
có fallback lưu mật khẩu rõ trong JSON/.env. Credential thuộc người dùng
Windows hiện tại trên máy này, theo [tài liệu CREDENTIALW của Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/wincred/ns-wincred-credentialw).

Kiểm thử UI dùng tài khoản giả và kho giả. Smoke Windows kiểm tra thật việc lưu,
liệt kê, đọc mật khẩu Unicode, đổi công ty, cập nhật và xóa hai tài khoản giả có
tên ngẫu nhiên; luôn xóa các mục giả sau kiểm thử. Smoke chạy ở cả source và
EXE độc lập. Không đưa credential hoặc nội dung hồ sơ thật vào bằng chứng build.
