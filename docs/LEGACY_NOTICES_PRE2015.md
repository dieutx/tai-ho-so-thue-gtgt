# Thông báo tờ khai legacy và hồ sơ trước 2015 — 21/10/2026

## Cập nhật có quyền ngày 21/10/2026

Sau báo cáo offline ban đầu, người dùng đã cấp quyền kiểm thử tài khoản thật.
Luồng desktop Worker đã đăng nhập, đọc 7 hồ sơ tháng 01/2020, tải 1 ZIP và
2 XML thông báo, rồi kiểm lại reuse mà không tải lại tệp hợp lệ. Kiểm chứng
EXE tương ứng được lưu riêng ở máy làm việc, không đưa dữ liệu thuế vào Git.

Các khác biệt thật được sửa bằng regression tổng hợp: header `Tải thông báo`
trên bảng legacy, header có ngắt dòng, số thông báo hiển thị khác messageId,
và namespace `http://kekhaithue.gdt.gov.vn/TBaoThue` của `TBaoThueDTu`.
Phản hồi CAPTCHA `Mã xác thực không chính xác` được phân loại đúng; XML tải
về không bị quét như trang đăng nhập.

Hai phép tra cứu tháng 12/2014 và tháng 01/2013 trả rỗng có xác nhận từ cổng.
Điều này chỉ mô tả đúng tài khoản/khoảng đã thử, không chứng minh mọi dữ liệu
trước 2015 đều không còn. Chưa có mẫu tải thật trước 2015 để xác nhận tệp cũ.

Phần dưới là ghi chép tại thời điểm kiểm thử offline ban đầu.

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
