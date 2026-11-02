# Pilot live được cấp quyền — 2.1.0

Người dùng đã cho phép trong hội thoại: một tài khoản do người dùng quản lý; chỉ tra cứu/tải tối đa 5 hồ sơ trong khoảng tối đa 7 ngày. Tài khoản/mật khẩu và CAPTCHA nhập trực tiếp trong ứng dụng, không gửi chat, không dùng `.env` để lấy secret cho pilot này.

Chạy `dist/TaiHoSoThue-Windows.exe --live-pilot`. Workspace/settings riêng: `%LOCALAPPDATA%/TaiHoSoThue/live-pilot/`. Mỗi task: tối đa 300 giây, 40 HTTP attempts kể cả redirect/retry, 2 trang, 20 MiB, 2 auth attempts, 5 records xử lý, nhịp tổng request ít nhất 1 giây. CAPTCHA thủ công, không stress test. Danh sách một trang có thể trả thêm metadata trước khi cap xử lý dừng. Không bật workers>1. Dừng ngay khi gặp 403/429/503 hay access verification.

1. Người dùng tự đăng nhập, bỏ lưu password nếu không muốn dùng vault hiện có.
2. Chọn mẫu ≤7 ngày năm 2025, Tra cứu rồi Tra cứu và tải; ghi counts từ SQLite và file tồn tại.
3. Chọn mẫu ≤7 ngày năm 2026; lặp lại, tổng kho không giảm.
4. Chuyển hai kỳ qua lại; request count của thao tác chỉ đổi kỳ phải bằng 0.
5. Đóng/mở EXE, Xem hồ sơ đã lưu, chọn đúng account; kiểm counts và tệp.
6. Tra cứu/tải lại, valid-existing download calls=0; nếu không có hồ sơ mới thực tế dùng test mock 100→105 đã có, không sửa hồ sơ thật.
7. Thử GNT/thông báo nếu được phép và có dữ liệu trong quota; offline/cancel không làm mất kho.
8. Chạy inspector read-only integrity/FK. Chỉ chia sẻ số tổng hợp; không commit DB/file/log/screenshot thuế thật.

Trạng thái ban đầu: **NOT_RUN — chờ người dùng nhập tài khoản trong ứng dụng**. Mọi bước không thực hiện được phải ghi NOT_RUN, không suy từ test mock. Pilot không đại diện toàn bộ nghiệp vụ/phiên hay chứng minh hỗ trợ concurrent download.
