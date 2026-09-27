# Stage 06 — Parser TNCN

Áp dụng master prompt. Phụ thuộc stage 04; tận dụng bài học stage 05. Chọn mẫu
TNCN thực sự có dữ liệu, ví dụ 05/KK-TNCN hoặc 05/QTT-TNCN nếu fixture xác nhận.
Chọn một mẫu/phiên bản cho MVP trước, không gộp khai khấu trừ và quyết toán
bằng một parser chỉ dựa trên tax_group.

Lập bảng hỗ trợ form code/schema version, field mapping/XPath/type/expected.
Parse thông tin chung, kỳ, lần nộp và chỉ tiêu của mẫu đã chọn; bảng chi tiết,
phụ lục có registry/capability riêng. Tách chỉ tiêu tổng hợp khỏi dữ liệu dòng.
Định nghĩa khóa dòng/quan hệ phụ lục với tờ khai, giữ raw id và order khi khóa
tự nhiên không được schema xác nhận. Không tự bỏ dòng trùng chỉ vì tên giống.

MST/CCCD/định danh là chuỗi, không đổi sang số hay làm mất số 0 đầu. Fixture
phải ẩn danh người lao động/phụ thuộc; log chỉ chứa artifact id và tên field lỗi,
không chứa danh sách thu nhập/CCCD. Parse offline, không gửi tờ khai tới OCR/LLM
API bên ngoài. Không tự suy diễn người cư trú/phụ thuộc/quyền giảm trừ từ dữ
liệu thiếu hoặc tự tính thuế theo quy định hiện hành.

Dùng Decimal và null semantics của framework. Mẫu/schema không hỗ trợ trả
unsupported; lỗi một dòng/field được mô tả rõ theo hợp đồng parser, không làm
output tổng hợp trông như đầy đủ khi bảng chi tiết bị bỏ qua.

Test golden JSON, nhiều dòng và phụ lục, tên/định danh leading zero, thiếu
optional fields, số âm/0, chính thức/bổ sung, XML namespace, version khác,
trường tổng hợp không khớp tổng dòng (warning nếu quan hệ được xác nhận),
re-run và log không lộ PII. Giao parser/mapping matrix, fixture ẩn danh,
expected output, CLI ví dụ và ghi rõ loại phụ lục chưa hỗ trợ.
