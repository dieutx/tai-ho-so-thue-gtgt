# Stage 01 — Ổn định nền tảng tải và chạy tiếp

Áp dụng master prompt. Đọc code mới trước: legacy trực tiếp, feature flag DVC,
summary cho skipped periods, phân nhóm metadata, atomic write từng file và
merge metadata đã có. Chỉ triển khai phần còn thiếu trong REVIEW.

Mục tiêu: một lần tải đáng tin cậy, có thể chạy tiếp, lỗi ở nguồn sau không làm
mất kết quả nguồn trước. Tách source policy khỏi giao thức portal. Login DVC
trì hoãn tới đoạn DVC đầu tiên; khi DVC tắt không được chạm host DVC.

Việc cần làm:

- Phân biệt empty hợp lệ, session expired, CAPTCHA lỗi, layout không hỗ trợ,
  network error và HTTP error trong PageResult/SearchError. Không suy luận
  empty chỉ từ HTTP 200; không ghi form lỗi vào trạng thái tốt.
- Re-login có giới hạn khi hết phiên; retry có giới hạn cho request an toàn,
  không retry tùy tiện login/form POST có trạng thái. HTTP Retry-After nhận
  số giây và HTTP-date, có trần chờ/cancellation.
- Sửa ưu tiên cấu hình lazy: CLI override hợp lệ không bị env bị override sai
  kiểu chặn. Validate giới hạn 31 ngày và khai báo page size/capability legacy.
- Identity phải bao gồm nguồn/tài khoản/mã hồ sơ; phân biệt found, downloaded,
  reused, failed, skipped. `--case-id` và dry-run phản ánh số thật.
- Giới hạn payload ZIP/XML; không đọc/decompress vô hạn. Review log URL,
  Referer, form/response/dump có DSE session/credential, redaction có kiểm thử.
- Giảm ghi toàn bộ metadata từng bản ghi khi số hồ sơ lớn; giữ checkpoint phù
  hợp. Có chiến lược phục hồi CSV/group index từ JSON authoritative, giữ field
  cũ chưa biết. Không hỗ trợ concurrent writers bằng lời nói khi chưa có lock.

Test bắt buộc: cutoff-1/cutoff/cutoff+1, khoảng mixed và cutoff tùy chỉnh,
DVC tắt không có HTTP/OCR call khi chỉ sau cutoff, login DVC lỗi sau khi legacy
đã lưu, timeout/429/session expired, trang lặp/rỗng bất thường, resume trùng mã
giữa hai nguồn/tài khoản, metadata hỏng/disk error, dry-run không đổi raw.

Giao: code + test + cập nhật chính sách nguồn và trạng thái lỗi. Nêu hạn chế
còn lại; chưa làm classifier XML hay parser nghiệp vụ trong stage này.
