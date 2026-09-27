# Stage 04 — Khung parser tờ khai

Áp dụng master prompt. Phụ thuộc stage 02–03. Không dùng `parsing.py` (HTML)
cho parser nghiệp vụ XML. Tạo package parser riêng và registry dispatch theo
format + tax group + form code + schema version + role; capability không có
parser trả unsupported có lý do, không fallback nhầm parser gần giống.

Thiết kế ParsedDeclaration versioned, tối thiểu có artifact/hash, case/source,
parser id/version, thông tin người nộp thuế, mã/tên mẫu, kỳ tính thuế (raw và
normalized nếu xác định được), loại/lần nộp, indicators, tables/appendices,
warnings/errors/status, field provenance (XPath/tag/raw value).

Tách thông tin chung và chỉ tiêu từng mẫu. Missing/null khác số 0; Decimal
cho số tiền, serialize theo hợp đồng rõ ràng. Không dùng float để biểu diễn
tiền. Ngày/kỳ lỗi phải giữ raw và báo warning, không tự đoán. Namespace và
schema version phải được xử lý rõ ràng. Không gộp nhiều lần nộp cùng kỳ.

XML reader an toàn dùng lại từ inventory/classifier, có giới hạn tài nguyên,
không mở external entity hay fetch schema trên mạng. Không sửa chữ ký XML;
việc parse dữ liệu không có nghĩa đã xác minh chữ ký. Lỗi một artifact không
dừng batch. Kết quả parse không ghi đè raw hoặc classifier output.

CLI offline parse artifacts, lưu kết quả theo identity + hash + parser version.
Cùng input/version phải deterministic và chạy lại không tạo bản trùng. Thay
version có thể reparse chỉ dữ liệu liên quan; preserve kết quả trước theo chính
sách version rõ ràng. Mock HTTP/solver để chứng minh lệnh offline không gọi mạng.

Test hợp đồng với fixture synthetic schema công khai trong test, không giả
mẫu synthetic là mẫu GDT thật. Có test namespace, Decimal, null/zero, date,
unknown/unsupported/conflict, corrupt XML, batch partial failures và reparse.
Giao framework, schema, registry, helper và hướng dẫn viết parser mới; parser
GTGT đầy đủ sẽ làm ở stage 05 với mẫu thực tế.
