# Master prompt

Bạn đang phát triển repo `tai-ho-so-thue-gtgt`, công cụ Python tải hồ sơ thuế.
Thực hiện STAGE = <điền 01..09> theo prompt chi tiết tôi gửi kèm. Đọc git status,
AGENTS.md nếu có, README.md, docs/ARCHITECTURE.md, docs/development/HANDOFF.md,
docs/development/REVIEW.md, docs/development/README.md và module/test liên quan. Đối chiếu code thực tế với
tài liệu; không lặp lại phần đã có và không sửa thay đổi riêng của người dùng.

Mục tiêu xuyên suốt:

1. Trước cutoff dùng trực tiếp legacy `thuedientu.gdt.gov.vn`. Cutoff mặc định
   01/07/2025, configurable. Ngày cutoff thuộc DVC. Không gửi bất kỳ request
   DVC nào khi DVC tắt, kể cả login/CAPTCHA. Mặc định DVC tắt; có thể mở lại sau.
2. Khoảng qua cutoff chỉ chạy nguồn bật; báo cụ thể đoạn bị bỏ qua và kết quả
   chưa đầy đủ. Không giả vờ thành công khi nguồn/trang/tải lỗi.
3. Tách Case, Artifact, Classification và ParsedDeclaration. Một hồ sơ/ZIP có
   thể chứa nhiều XML/PDF/phụ lục/thông báo, mỗi file có phân loại riêng.
4. GTGT/TNCN/TNDN là nhóm thuế; chính thức/bổ sung là loại lần nộp; XML/PDF/ZIP
   là định dạng. Không dùng một trường cho nhiều ý nghĩa.
5. Parser dispatch theo nhóm + mã mẫu + schema version + format. UNKNOWN,
   unsupported, conflict và failed là kết quả hợp lệ, có lý do; không đoán.
6. Giữ nguyên raw file, hash và provenance. Có thể phân loại/parse lại offline
   không cần tài khoản/OCR/kết nối cổng. Output có schema/rule/parser version.
7. Nội dung thuế được lấy từ fixture và nguồn chính thức khi cần xác minh.
   Không bịa mã mẫu, XPath, chỉ tiêu hoặc công thức. Decimal cho số tiền,
   phân biệt missing/null/zero; không tự tính nghĩa vụ thuế không được yêu cầu.

Quy trình cho một lần phát triển:

- Chạy baseline cần thiết; tóm tắt bằng chứng về phần còn thiếu và phạm vi sửa.
- Triển khai stage được chọn tới kết quả dùng được. Ưu tiên giải pháp nhỏ theo
  kiến trúc repo, không gom thành một module lớn hoặc rewrite không cần thiết.
- Chỉ thêm dependency khi thư viện chuẩn/thư viện đã có không đáp ứng; ghi lý do.
- Test offline bằng fixture ẩn danh: happy path, lỗi, ranh giới, resume và tương
  thích dữ liệu cũ. Không gọi cổng thật hoặc dịch vụ OCR ngoài trong unit test.
- Chạy unittest, ruff, mypy theo CI; có vấn đề môi trường thì sửa trong môi
  trường riêng, không đổi môi trường/tài khoản người dùng ngoài phạm vi.
- Cập nhật README, kiến trúc, REVIEW, HANDOFF và trạng thái stage; viết lệnh chạy
  mẫu, ghi phần đã xong/còn thiếu và bước tiếp theo để chuyển máy không mất ngữ cảnh.
- Báo kết quả đã làm, kiểm thử, hạn chế và stage tiếp theo; dừng ở ranh giới
  stage được chọn. Không tự chuyển sang stage kế tiếp, bật DVC mặc định, push,
  deploy hay gửi dữ liệu cho bên thứ ba.

Quy tắc thực thi: không in hay chép bí mật `.env` vào output/tài liệu; chỉ dùng
cấu hình tài khoản để test thật khi người dùng yêu cầu, qua luồng cấu hình của
ứng dụng, trên khoảng được cho phép. Không commit credentials hoặc
fixture thật chưa ẩn danh. Dump HTTP thô là dữ liệu riêng tư, chưa mặc định an
toàn để chia sẻ. Tải ngay trong từng trang để giữ trạng thái phiên của cổng.
Nếu thiếu mẫu cho parser, hoàn thành framework/fixture harness/phần độc lập,
ghi rõ thiếu mẫu nào và hỏi dữ liệu cần thiết; không đánh dấu parser hoàn thành.

Tiêu chí giao stage: code hoạt động với dữ liệu kiểm chứng, test bảo vệ nghiệp
vụ, tài liệu đúng hành vi, không mất raw/metadata cũ, mặc định legacy/DVC đúng,
không có placeholder được mô tả như tính năng hoàn chỉnh.
