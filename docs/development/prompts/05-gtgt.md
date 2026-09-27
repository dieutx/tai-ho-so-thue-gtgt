# Stage 05 — Parser GTGT đầu tiên

Áp dụng master prompt. Phụ thuộc stage 04. Chọn đúng một mã mẫu GTGT và một
schema version xuất hiện trong fixture có nguồn kiểm chứng. Nếu dữ liệu có
01/GTGT thì có thể chọn mẫu đó; không coi mọi XML nhóm GTGT là 01/GTGT.

Đầu tiên lập bảng fixture → root/namespace → form code/version → field/XPath
→ kiểu → required/optional → expected output. Ẩn danh MST, tên, địa chỉ, thông
tin cá nhân nhưng giữ schema và quan hệ số liệu cần test. Không dùng regex tên
file để thay cấu trúc XML. Thiếu mẫu thực tế: hoàn thành mapping harness/phần
độc lập, ghi rõ thiếu mẫu, không tuyên bố hỗ trợ mẫu GDT.

Parser lấy thông tin chung, kỳ, loại/lần nộp và các chỉ tiêu hiện diện trong
mẫu đã chọn. Chỉ tiêu cần danh sách có kiểm chứng, không bịa XPath/chỉ tiêu số
21..43 từ trí nhớ. Dùng Decimal, missing/null/zero khác nhau. Giữ raw và XPath
cho mỗi giá trị để kiểm tra đối chiếu; normalization số dựa trên format fixture.

Phân biệt tờ khai chính, phụ lục và thông báo trong ZIP. Tờ khai bổ sung và
chính thức là các bản khác nhau; không tự thay thế hay cộng dồn số của chúng.
Không tự tính số thuế phải nộp nếu không được yêu cầu; consistency check chỉ
thêm warning dựa trên quan hệ được tài liệu/fixture xác nhận.

Test golden output cho chính thức/bổ sung nếu có mẫu, namespace, chỉ tiêu
vắng/rỗng/0/âm, kỳ tháng/quý, schema khác không hỗ trợ, XML hỏng và cùng nhóm
nhưng mã mẫu khác. Nếu mẫu chỉ có kỳ tháng, ghi rõ hỗ trợ kỳ quý chưa kiểm chứng.
Giao parser đăng ký trong framework, fixture ẩn danh, golden JSON, bảng mapping,
lệnh offline từ ZIP đến parsed output và danh sách phạm vi hỗ trợ chính xác.
