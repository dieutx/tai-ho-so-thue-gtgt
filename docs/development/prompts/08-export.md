# Stage 08 — Xuất và truy vấn dữ liệu đã parse

Áp dụng master prompt. Phụ thuộc tối thiểu parser GTGT có kiểm chứng; dùng TNCN/
TNDN khi đã hoàn thành. Mục tiêu: người dùng tìm được hồ sơ theo nhóm, tài khoản,
kỳ, mã mẫu, ngày nộp và lần nộp; truy vết được mỗi số tới file gốc.

Triển khai CLI offline query/export từ manifest và parsed output. Có bộ lọc
tax_group/form/version/period/submission/status và export CSV/JSON; Excel chỉ
thêm khi thực sự cần và có thư viện/skill phù hợp. Không đưa logic portal vào
export, không yêu cầu credential/OCR/network cho các lệnh này.

Tách bảng tờ khai, chỉ tiêu dạng dài, bảng phụ lục/chi tiết, danh sách failed/
unsupported/unknown/conflict. Thể hiện identity, hash, source, rule/parser
version và provenance. Giữ cột định danh dạng chuỗi, Decimal không mất độ chính
xác, null khác 0. CSV UTF-8 BOM, escape công thức spreadsheet bắt đầu `=,+,-,@`
cho trường text theo chính sách rõ ràng, không biến tiền âm thành text sai.

Không chọn bản bổ sung mới nhất hay hợp nhất nghĩa vụ thuế một cách ngầm. Nếu
có view latest, định nghĩa thứ tự bằng ngày/lần nộp và xử lý tie/missing riêng,
vẫn xuất được lịch sử đầy đủ; không cộng số của nhiều lần nộp cùng kỳ.

Đo số hồ sơ/member/dung lượng, thời gian inventory/classify/parse/export,
RAM và số lần ghi. Dựa trên số liệu chọn snapshot/journal/SQLite nếu cần.
Hỗ trợ resume/reparse chọn lọc theo hash + phiên bản; atomic outputs và lock
writer nếu công bố hỗ trợ nhiều tiến trình. Chưa cần GUI.

Test golden exports, nhiều nhóm/kỳ/bản nộp, text có dấu/phẩy/newline/leading
zero/công thức, tiền âm/chính xác lớn, lỗi một artifact và filtering không làm
mất lịch sử. Giao lệnh mẫu, schema dữ liệu xuất, benchmark tái lập được,
báo cáo coverage/parser failures và tài liệu giới hạn.
