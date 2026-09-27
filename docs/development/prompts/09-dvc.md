# Stage 09 — Chuẩn bị mở lại DVC khi cần

Áp dụng master prompt. Stage này chỉ làm khi được chọn rõ ràng; không phải điều
kiện để phát triển inventory/classification/parser offline. DVC vẫn mặc định
tắt sau stage, mở bằng --enable-dvc hoặc GDT_DVC_ENABLED=true.

Đọc các adapter DvcPortal/EtaxPortal, auth/CSRF/pagination và source policy.
Xác minh endpoint/layout bằng fixture mới có nguồn khi được cấp dữ liệu hoặc
phạm vi thử thật. Không coi fixture cũ/test offline là bằng chứng cổng hiện tại
hoạt động. Khi chạy thật, chỉ dùng tài khoản và khoảng nhỏ nằm trong phạm vi
được chỉ định; không quét thêm tài khoản/khoảng ngày ngoài yêu cầu.

Đăng nhập mỗi host có phiên riêng, lazy khi chạm nguồn. Legacy trước cutoff
không phụ thuộc DVC login thành công. Chặn mọi request DVC khi feature flag tắt,
kể cả validate/detail/download/CAPTCHA/fallback; test ở biên HTTP/factory.

Kiểm chứng CSRF mới, phân trang, trạng thái validate và form download fallback.
Không coi lỗi business validate như endpoint không khả dụng rồi bỏ qua guard.
Trang hết phiên/layout sai phải ra lỗi riêng, không empty giả. Giữ tải ngay
trên từng trang để không mất trạng thái validate. File mới đi qua cùng storage/
inventory/classification, không cần sửa từng parser.

Test legacy-only, DVC-only và mixed ở cutoff/custom cutoff, DVC enabled/disabled,
disable CLI override env enabled, login DVC thất bại sau legacy thành công,
HTTP 429/403/500, CAPTCHA/CSRF hết hạn, repeated pages, raw/base64 ZIP và tên
file không an toàn. Fixture phải ẩn danh credential/session/dữ liệu thuế.

Giao adapter tương thích fixture mới, test regression, tài liệu bật/tắt và
rollback flag. Nêu riêng điều đã xác minh offline và điều xác minh thật.
Không tự bật DVC mặc định chỉ vì hoàn thành stage này.
