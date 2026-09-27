# Stage 03 — Phân loại từng file theo nội dung

Áp dụng master prompt. Phụ thuộc stage 02. `metadata-keyword-v1` hiện là gợi ý
cấp hồ sơ. Mục tiêu mới là Classification cho từng Artifact, không gán cả ZIP
vào nhóm của một file hay phân loại phụ lục như tờ khai chính.

Định nghĩa các chiều riêng: tax_group (GTGT/TNCN/TNDN/OTHER/UNKNOWN),
document_role (declaration/appendix/notice/receipt/unknown), form_code,
schema_version, format, rule_version, evidence và trạng thái conflict/unknown.
Đừng lấy `loai_to_khai=Chính thức/Bổ sung` làm tax_group.

Xây registry/rules dễ bổ sung, thuần và deterministic. Với XML, ưu tiên dấu
hiệu nội dung được kiểm chứng: root/namespace, mã mẫu, tên mẫu và trường phiên
bản. Metadata portal/tên file chỉ là evidence phụ. Quy tắc mã mẫu có bảng ánh
xạ có nguồn/fixture; không lấy số form phổ biến rồi áp cho mọi phiên bản.
Khi nội dung mâu thuẫn metadata, giữ cả hai evidence, ghi quyết định hoặc
conflict theo chính sách rõ ràng. Thiếu tín hiệu không được tự gán GTGT.

XML reader không resolve entities/DTD, không fetch mạng, có giới hạn bytes/
depth. PDF chưa có parser/OCR thì có thể phát hiện format và role ở mức hỗ trợ;
không kéo OCR nặng vào stage này. File không hỗ trợ vẫn nằm trong manifest.

Thêm CLI offline phân loại/reclassify từ inventory; lưu schema và rule version,
có thể chạy lại sau khi thêm rule mà không tải lại raw. Xuất danh mục nhóm theo
artifact và danh sách unknown/conflict để người dùng bổ sung mẫu. Không di
chuyển raw để thể hiện phân nhóm.

Test: GTGT/TNCN/TNDN có/không namespace, schema khác, tên file sai, metadata
mâu thuẫn, appendix/notice cạnh tờ khai chính, nhiều nhóm trong cùng ZIP,
missing code/version, XML lỗi, deterministic re-run và thêm rule mới không sửa
pipeline. Giao rule matrix, bằng chứng, fixtures và lệnh sử dụng.
