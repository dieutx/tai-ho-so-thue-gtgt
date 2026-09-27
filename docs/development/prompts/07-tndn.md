# Stage 07 — Parser TNDN

Áp dụng master prompt. Phụ thuộc stage 04, ưu tiên sau GTGT MVP. Chọn mẫu TNDN
từ fixture đã ẩn danh và biết nguồn; có thể chọn 03/TNDN khi dữ liệu xác nhận.
Không gán báo cáo tài chính hoặc mọi phụ lục có chữ TNDN thành tờ khai chính.

Lập support matrix theo form code, schema version, role và format. Mapping
thông tin chung, kỳ năm/kỳ đặc biệt, chính thức/bổ sung, chỉ tiêu và phụ lục
dựa trên XML thực tế. Ghi rõ các phần không có fixture thay vì giả hỗ trợ.

Tách tờ khai chính khỏi bảng/phụ lục. Liên kết phụ lục theo id/schema/provenance,
không dựa tên ZIP đơn thuần. Giữ loại/kỳ gốc nếu kỳ không chuẩn, normalize chỉ
khi đủ bằng chứng. MST/id là chuỗi; tiền và tỉ lệ theo kiểu Decimal và đơn vị
được xác minh trong mapping. Missing/null/0 phải khác nhau.

Không tự tính lại thuế suất, chuyển lỗ, ưu đãi hoặc nghĩa vụ thuế. Parser trích
xuất số khai trong tài liệu. Chỉ thêm consistency warning khi có quan hệ toán
học được fixture/tài liệu chính thức xác nhận, không biến warning thành sửa số.

Test chính thức/bổ sung nếu có dữ liệu, số âm/0, nhiều bảng/phụ lục, schema
khác, kỳ năm không trùng lịch nếu fixture có, báo cáo tài chính trong cùng ZIP,
lỗi chỉ tiêu/batch partial failure, round-trip Decimal và reparse theo parser
version. Giao parser đăng ký, fixture/golden output, bảng XPath/type/source,
lệnh offline và phạm vi hỗ trợ. Thêm form/version mới bằng đăng ký parser,
không thêm nhánh TNDN trong pipeline tải.
