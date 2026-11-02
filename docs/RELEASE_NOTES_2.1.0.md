# Tải Hồ Sơ Thuế 2.1.0 — Kho local và đối soát bổ sung

- Giữ bộ chọn kỳ và hai ngày sau tra cứu/tải; có thể đổi kỳ trực tiếp.
- SQLite tích lũy hồ sơ theo tài khoản, nguồn và mã hồ sơ. Chuyển kỳ, đóng/mở app và tra cứu lỗi không xóa lịch sử.
- Đổi kỳ đọc ngay dữ liệu trên máy; tra cứu online bổ sung/cập nhật. Tra cứu và tải dùng lại tệp hợp lệ, lấy phần còn thiếu.
- Import JSON cũ có kiểm tra ownership, backup và quarantine; giữ nguyên ZIP/XML/PDF/evidence gốc. Ngày chưa rõ có nhóm riêng.
- Đọc local khi offline, lưu ngày theo tài khoản/tab, tách số tổng kho và số trong kỳ.
- Checkpoint SQLite từng hồ sơ; export JSON/Excel một lần khi kết thúc để giảm việc ghi lại toàn danh sách.

Kiểm chứng source build 07fcfd3: 911 unit/integration tests (6 skips); ruff/mypy; Windows onefile Full/CPU OCR, bundle audit, hai lượt frozen smoke và 18/18 cấu hình native DPI PASS. Mock 100→105 giữ đúng 105 keys, 98 tệp reused, đúng 7 download calls; chạy lại không gọi download cho 105 tệp đã hợp lệ. Migration fixture không đổi SHA-256 tệp gốc. [Báo cáo triển khai](IMPLEMENTATION_REPORT_2.1.0.md) ghi checksum và giới hạn kiểm chứng.

Giữ nguyên luồng CAPTCHA tự động: OCR và fallback tối đa 5 lượt tự động trước nhập tay được kiểm tra trong frozen smoke; không đổi GuiCaptchaSolver hoặc module OCR/portal trong lượt hoàn thiện này.

Benchmark metadata tổng hợp 100.000 rows: median đọc/lọc JSON 600,132 ms, SQLite SELECT tháng tương ứng 46,053 ms (5 warm reads); không đại diện tốc độ cổng thuế thật.

Giới hạn: tải vẫn tuần tự; chưa bật nhiều worker vì chưa chứng minh session DSE/CSRF độc lập. Pilot live chỉ báo PASS cho bước có bằng chứng thực; trạng thái chi tiết được cập nhật trong báo cáo triển khai. Không coi mock/frozen smoke là kiểm thử tài khoản thuế thật.

Hướng dẫn dữ liệu/rollback: [LOCAL_DATABASE_GUIDE](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/feature/persistent-catalog-smart-sync/docs/LOCAL_DATABASE_GUIDE.md).
