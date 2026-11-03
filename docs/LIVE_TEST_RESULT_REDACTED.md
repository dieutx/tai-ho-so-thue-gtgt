# Kết quả live — 2.1.0, tiếp tục ngày 02/11/2026

**Trạng thái: NOT_RUN cho nghiệm thu nghiệp vụ live.** Lượt tiếp tục này chỉ chạy unit/integration, portal giả, UI fixtures và build/smoke offline. Chưa có phiên đăng nhập do người dùng hoàn tất để kiểm chứng hồ sơ thật; không lấy mật khẩu từ `.env`, không tự đọc credential thuế từ vault.

Tiến độ trước đó ghi nhận pilot đăng nhập đã hủy sau 6 requests, chưa discovery/download. Đây không phải bằng chứng PASS cho tra cứu, tải, persistence nhiều năm hoặc tốc độ trên cổng thuế.

| Hạng mục | Kết quả |
|---|---|
| L1 đăng nhập live thành công | NOT_RUN trong lượt tiếp tục |
| L2–L3 tra cứu/tải mẫu 2025 và 2026 | NOT_RUN |
| L4–L6 chuyển kỳ/restart/tra cứu lại với dữ liệu thật | NOT_RUN; chỉ có mock và frozen smoke |
| L7 phát hiện hồ sơ mới | Mock 100→105 PASS; live NOT_RUN |
| L8 offline/hủy với kho thật | NOT_RUN; regression synthetic PASS |
| L9 GNT/thông báo live | NOT_RUN; adapter mock PASS |
| L10 so sánh worker 1/2 | NOT_RUN; giữ tải tuần tự |
| L11 integrity/checksum kho thật | NOT_RUN; fixture PASS |
| L12 bảo vệ dữ liệu chia sẻ | Báo cáo này không chứa MST, credential hay hồ sơ thật |

Chạy pilot tiếp theo theo [LIVE_TEST_PROTOCOL.md](LIVE_TEST_PROTOCOL.md), nhập tài khoản/CAPTCHA trực tiếp vào ứng dụng. Không suy kết quả live từ test offline; chưa công bố full E2E PASS.
