# Mapping và định dạng số

CORE-08/09: mỗi field có `numeric_format` (`xml_decimal`, `vi`, `en`, hoặc
`auto`). Mapping đóng gói khai `xml_decimal`, phù hợp fixture XML đã kiểm chứng;
`auto` chỉ giữ tương thích cho custom mapping và trả warning khi một dấu phân
cách có thể mang hai nghĩa, như `1.234`. Grouping sai như `12.34.56` bị từ chối.
Raw text được giữ, giá trị lỗi không đổi thành 0. ID/MST phải dùng datatype string.

`load_registry()` mặc định strict đối với mapping đóng gói. Custom directory
giữ chế độ tolerant để tương thích, nhưng có `diagnostics` và warning ở kết quả
parse; dùng `strict=True` để chặn mọi lỗi cấu hình. Duplicate key bị từ chối,
trừ `allow_override=True` tường minh có audit `overrides`. Không tự overlay
custom directory lên registry đóng gói.

`supported_versions` giới hạn các wildcard mapping đóng gói theo dữ liệu đã
kiểm chứng. Version mới trả NEED_MAPPING; không suy ra mapping từ mã mẫu.
`detect.root`/`namespace` được kiểm trong extraction/classification. Effective
dates, nếu có, áp theo ngày bắt đầu kỳ khai được xác định rõ; thiếu ngày không
áp mapping có ràng buộc đó. Không dùng ngày tải tệp làm ngày hiệu lực thuế.

`required` mặc định false cho field cũ. Field required thiếu hoặc giá trị lỗi
được phản ánh bằng `validation_status=PARTIAL`/`EXTRACTION_INCOMPLETE`, tách khỏi
`status=MAPPED` chỉ nói rằng có mapping. Mapping/registry fingerprint không phụ
thuộc đường dẫn máy và sẽ được mang vào audit/lineage ở PR export.

Mapping version đóng gói tăng lên 2 vì contract metadata/number policy thay đổi;
không thay ý nghĩa chỉ tiêu hoặc tên canonical đã kiểm chứng. Các note lịch sử
về `form_version=null` phải được đọc cùng `supported_versions` của runtime.
