# Thông báo tờ khai legacy và hồ sơ trước 2015 — 21/10/2026

Bản 2.0.1 hợp nhất phần core và nhánh legacy. Không đăng nhập hoặc tải hồ sơ
thật trong lượt này; các ca kiểm chứng dùng fake transport/fixture offline.

## Luồng thông báo

Đọc `ctMaGDich` từ `thongBao(...)` trên đúng hàng tờ khai; mã này khác
`messageId` của ZIP. Mở `viewTBao`, đọc bảng `tbl_tracuu` và dùng form
`tkhaiForm`/trạng thái DSE do trang trả về để tải từng XML/PDF.
Thông báo được kiểm tra loại tệp, hash, nguồn legacy, tài khoản và hồ sơ cha.
Chạy lại dùng lại tệp có bằng chứng khớp; lỗi thông báo không làm mất ZIP.

Trang thiếu form/bảng, thay handler, chỉ đọc được một phần hoặc còn phân trang
được ghi là chưa đầy đủ. Bản này không tự duyệt trang thông báo chưa có hợp
đồng đã kiểm chứng; giữ các mục đã đọc được và báo lỗi discovery.
Tiêu đề gộp “Chấp nhận/Không chấp nhận” không chứng minh kết quả tiếp nhận.
Đường dẫn trong `attachment_result.items[].path` tương đối với nơi lưu đầu ra.

## Kết quả kiểm tra trước 2015

- Không có mốc chặn `01/01/2015` trong query legacy, cấu hình ngày hoặc UI.
  Test gửi đủ khoảng 01/01–31/03/2013 qua từng đoạn tối đa 31 ngày.
- Bộ đọc XML core trước tích hợp từ chối mọi DOCTYPE. Điều này có thể chặn
  XML schema cũ ngay cả khi portal trả tệp đúng; chưa có hồ sơ thật để kết
  luận đây là nguyên nhân trường hợp người dùng gặp.
- Reader chung nay nhận DOCTYPE không ENTITY, không nạp DTD, không gọi mạng;
  vẫn kiểm giới hạn byte/depth/node và từ chối ENTITY cả UTF-16.
- ZIP trả trực tiếp được kiểm đúng loại tờ khai trước khi lưu; HTML/XML lỗi,
  ZIP giả và tài liệu sai loại vẫn bị từ chối. Download, save/resume và
  offline cùng sử dụng policy; tăng phiên bản parser/profile/validator.

Các test cũng kiểm thông báo đúng nguồn, trạng thái chưa đầy đủ khi trang lạ,
giữ ZIP khi lỗi thông báo, dùng lại tệp, metadata CLI/desktop tương đương và
chỉ số bảng Qt cũ. Việc tra cứu trả rỗng không đủ chứng minh cổng đã xóa hồ sơ;
cần đối chiếu tài khoản, quyền, khoảng ngày và kết quả trên portal nếu còn lỗi.
