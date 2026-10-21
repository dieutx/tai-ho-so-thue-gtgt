# Sửa bảng tờ khai DVC — 22/10/2026

Người dùng gặp `SCHEMA_CHANGED: REQUIRED_COLUMNS_MISSING_OR_AMBIGUOUS:lan_nop`
trên EXE 2.0.3. Đã tái hiện đúng mã lỗi bằng Worker production với tài khoản
có quyền; không ghi HTML, credential hoặc giá trị hồ sơ vào fixture/Git.

Hai khác biệt cấu trúc được quan sát trên DVC tháng 09 và 10/2026:

- Tiêu đề `Lần nộp (Tờ khai)/File số (DLVC)` thay cho `Lần nộp`.
- Bảng có 13 tiêu đề; hàng hồ sơ có 12 ô, bỏ ô cuối `Hồ sơ đính kèm`.

Thêm alias đúng cho schema DVC. Cho phép thiếu cột đã khai tùy chọn ở cuối
hàng; không đoán vị trí cột giữa, không bỏ cột bắt buộc hoặc bỏ hàng lỗi.
Contract tăng thành `portal-table-v4`. Test kiểm toàn bộ trường trước/sau,
đảo cột, header rowspan, cột trùng, cột lạ và số lần nộp không hợp lệ.
Smoke source/frozen dùng bảng tổng hợp với chính tiêu đề và hàng 12 ô này.

Lỗ hổng kiểm chứng trước đó: online-check chỉ dùng mặc định `dvc=False`, nên
chứng cứ legacy 01/2020 không xác minh bảng DVC. Nay request có boolean `dvc`
tường minh (chỉ áp dụng chế độ tax); report ghi cờ này và nguồn thực tế của
các hàng. Request cũ giữ mặc định false, không tự mở thêm nguồn.

Kiểm thử source có quyền sau bản sửa: DVC 09/2026 đọc 24 hồ sơ, 01–22/10/2026
đọc 10 hồ sơ, legacy 06/2025 đọc 2 hồ sơ; cả ba `SUCCESS`, 5 trang/27 request.
Đây là kiểm thử tra cứu, chưa chứng minh tải tệp; không gọi kết quả Python
là kết quả EXE. Báo cáo frozen và receipt bàn giao được lưu riêng khi build
hoàn tất trong `dist/release-manifest.json` và PROGRESS tại máy làm việc.

Kiểm thử thật dùng thư mục `.cache` riêng, giữ nguyên thư mục hồ sơ người dùng.
Không có yêu cầu publish/tag/replace release trong lượt sửa lỗi này.
