# Rà soát thông báo cơ quan thuế theo từng tờ khai — 22/10/2026

Đã kiểm tra phần hiển thị, đọc XML, liên kết hồ sơ và xuất báo cáo ở checkout
gốc và checkout tích hợp `.cache/pr-worktrees/main-integration`. Các sửa đổi
trong lượt này chưa commit, chưa có trong EXE đã build trước đó.

## Trình bày

- Cột **Thông báo** hiển thị trạng thái và `Mở N tệp` trên hai dòng. Bấm ô,
  nút trong khung chi tiết hoặc menu chuột phải để chọn đúng tệp.
- Chấp nhận: xanh; không chấp nhận: đỏ và nền dòng hồng; tiếp nhận: trung tính.
  Trạng thái cơ quan thuế trên danh sách và trạng thái ZIP vẫn là các trường
  riêng. Thông báo từ chối không bị tính thành lỗi tải ZIP.
- Có tệp nhưng không xác định được nội dung: **Chưa xác định**, vẫn mở được.
  Không có tệp trên máy chưa có nghĩa là cổng không có thông báo.
- Bộ lọc **Cần kiểm tra** nhận cả trường hợp từ chối đọc từ XML. Tìm kiếm
  nhận số thông báo, tiêu đề và lý do từ chối.
- Khung chi tiết hiển thị số/ngày thông báo, lý do, đường dẫn tương đối và
  tình trạng đối chiếu tham chiếu/checksum. PDF/ZIP đính kèm được liệt kê để
  mở; không suy ra trạng thái nghiệp vụ từ tên các tệp này.

Ảnh minh họa dùng dữ liệu giả, không chứa hồ sơ thật:
[bảng](../.cache/optimization/notice-review-preview/table-1366x768.png),
[chi tiết](../.cache/optimization/notice-review-preview/detail-1024x600.png).
Đã xem ảnh ở ba work area 1366×768, 1024×600, 853×480 bằng Qt offscreen.
Đây không phải kiểm chứng native EXE/DPI mới.

## Lưu trữ và tham chiếu

Giữ cách lưu hiện có, không tạo bản sao XML hay đổi tên dữ liệu cũ:

```text
<nơi lưu tờ khai của tài khoản>/
  danh_sach_ho_so.json
  thong-bao-dinh-kem/
    <mã hồ sơ trên cổng>/
      <mã thông báo>__<loại>__<mã hồ sơ>__<tiêu đề>.xml
      <tên tệp>.xml.integrity.json
```

Ở **core tích hợp**, định danh hồ sơ gồm tài khoản, nguồn, loại hồ sơ và mã
trên cổng (`RecordKey`). Định danh đính kèm (`AttachmentKey`) chứa khóa hồ sơ
cha, nguồn tải, ID thông báo và tham số phân loại/tra cứu. Tên thư mục chỉ là
vị trí lưu; không đủ làm bằng chứng tệp thuộc hồ sơ đang xem.

- `attachment_result` trong metadata giữ khóa cha, khóa thông báo, đường dẫn
  tương đối, SHA-256, dung lượng, kết quả tải/reuse và độ đầy đủ.
- Sidecar `.integrity.json` giữ nguồn, khóa cha và checksum của tệp. UI mới
  đối chiếu khóa cha, mã hồ sơ, dung lượng và hash trước khi kết luận trạng
  thái của hồ sơ có ownership. Khóa cha khác tài khoản hoặc nguồn bị loại.
- Tệp cũ thiếu sidecar vẫn có thể mở, được ghi rõ chưa xác minh tham chiếu.
  Với hồ sơ đã có ownership, không dùng tệp chưa xác minh để kết luận chấp
  nhận/từ chối. Tệp không khớp checksum được báo cần kiểm tra.
- XML trên 4 MiB vẫn được liệt kê nhưng chưa parse/đối chiếu checksum tại UI.
  Việc đọc để hiển thị không gọi mạng, không viết lại XML/sidecar/metadata.
- Các trường `_notices`, `_notice_state`, `_notice_summary` chỉ phục vụ UI,
  được dựng lại từ tệp tại lần kiểm tra; không là kho tham chiếu thứ hai.

Checkout gốc còn dùng core cũ, chưa có `RecordKey`/sidecar khi tải. Phần giao
diện và parser được sửa tương thích ở đó; không tuyên bố core cũ đã có cơ chế
ownership của checkout tích hợp.

Xuất Excel nay có trạng thái/số tệp thông báo trong **Danh sách hồ sơ**, và
sheet **Thông báo tờ khai**: mã hồ sơ, nguồn, khóa cha, số/ngày/tên, lý do,
đường dẫn từ nơi lưu tờ khai, khóa thông báo, SHA-256, dung lượng và tình trạng
đối chiếu. Sheet `Attachments` của core tích hợp vẫn giữ tình trạng tải/độ đầy
đủ. Báo cáo không sao chép tệp gốc; chuỗi XML được ghi thành text, không thành
công thức Excel.

## Lỗi đã sửa và kiểm chứng

1. XML hỏng/tệp chỉ có tên “chấp nhận” không còn tạo kết luận chấp nhận.
   Mã trạng thái chưa hiểu để **Chưa xác định**, không tự coi là thành công.
2. Đọc cả lý do lồng trong `LyDo/CTietLyDo`, không bỏ sót text ở phần tử con.
3. Sửa bộ lọc Cần kiểm tra, tìm kiếm theo thông báo, nhãn tệp chưa đọc được
   và bổ sung tham chiếu trong Excel.
4. Kiểm thử qua chính `NoticeStore` rồi `verify_rows`: cùng mã hồ sơ nhưng
   khác tài khoản/nguồn không bị gộp nhầm; tệp bị thay đổi không được coi là
   thông báo đã xác minh.

- Core tích hợp: **758 tests, 752 đạt, 6 skip** OCR tùy chọn.
- Minimal tích hợp: **758 tests, 712 đạt, 46 skip** capability tùy chọn.
- Checkout gốc: **522 tests, 515 đạt, 7 skip** gồm OCR tùy chọn và bài chỉ dành
  cho core identity mới. Ruff đạt ở cả hai; mypy đạt 91 file với tooling pin.
- Đọc lại **5 XML thật có sẵn trong cache**: 5/5 parse và đối chiếu tham chiếu/
  checksum đạt; 3 tiếp nhận, 2 chấp nhận. Không đăng nhập thêm cho bước này;
  không đưa dữ liệu thật vào fixture, ảnh minh họa hay báo cáo này.

Trạng thái tổng hợp ưu tiên từ chối nếu có nhiều kết quả; chỉ phản ánh tệp
đã đọc được trên máy, không chứng nhận cổng đã trả đầy đủ hoặc XML có chữ ký
hợp lệ. XML chưa hỗ trợ và PDF/ZIP chưa được diễn giải nội dung.

## EXE còn chờ

EXE 2.0.4 đã có trước lượt review gắn commit `0555b66`, qua offline/OCR/UI
trước đó. Lượt online lần này dừng ở login với `AUTH_INVALID_CREDENTIALS`;
không lặp lại đăng nhập, chưa cập nhật EXE mặc định và chưa chạy bàn giao.
Các thay đổi mới phải được commit, build và kiểm chứng đúng artifact trước
khi bàn giao/publish. Không dùng receipt/build của commit cũ để xác nhận mã
nguồn mới.
