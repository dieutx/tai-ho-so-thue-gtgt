# Tra cứu theo mã và cập nhật trạng thái — 04/11/2026

## Hành vi

Mỗi lần mở ứng dụng dùng mặc định **Doanh nghiệp**, khoảng **30 ngày gần nhất**
(hôm nay và 29 ngày trước), cho cả tờ khai, giấy nộp tiền và thông báo.
Hai lựa chọn Doanh nghiệp/Cá nhân luôn hiện cạnh nhau, hỗ trợ chuột và bàn phím;
đổi loại tài khoản vẫn đăng xuất và tách kho, bị chặn khi đang chạy tác vụ.
Kỳ tự chọn được giữ trong cùng phiên; mở lại ứng dụng bắt đầu khoảng mới,
các hồ sơ cũ vẫn xem được khi đổi kỳ. Có preset “30 ngày gần nhất”.

`Tải chưa tải`, `Thử lại tệp lỗi`, `Tải các tệp đã chọn` và `Cập nhật đã chọn`
dùng từng mã hồ sơ trong tài khoản/nguồn đã xác minh. Các trường gửi lên cổng:

| Nguồn | Trường lọc |
|---|---|
| DVC, cả cá nhân và doanh nghiệp | `maHoSo` |
| Thuế điện tử trên DVC | `maGiaoDichTthc_tdt` |
| Thuế điện tử doanh nghiệp cũ | `ma_gd` |
| Thuế điện tử cá nhân cũ | `maGDich` |

Ngày nộp đã lưu giúp chọn đúng đoạn ngày để tra cứu. Ngày nằm ngoài kỳ đang chọn
không được dùng làm lý do bỏ qua hồ sơ; ứng dụng vẫn gửi truy vấn theo mã.
Kết quả chỉ được xử lý khi khớp chính xác tài khoản, nguồn và mã đã chọn.
Nếu cổng trả một danh sách khác thay vì mã yêu cầu, ứng dụng báo lỗi và dừng
quét trang. Hồ sơ có lỗi tải không kích hoạt việc tìm lại hàng loạt trong các kỳ sau.
Giấy nộp tiền và thông báo độc lập giữ adapter riêng của từng nghiệp vụ.

`Cập nhật đã chọn` dùng lại ZIP hợp lệ, cập nhật metadata, trang chi tiết và
phản hồi đính kèm; tệp thiếu được tải bổ sung. Có thể cập nhật một hồ sơ từ menu
chuột phải hoặc khung chi tiết.

## Trạng thái CQT

1. Đọc trạng thái từ kết quả tra cứu.
2. Khi tải/cập nhật, đọc lịch sử chi tiết DVC (`timeline-step`, `Trạng thái hồ sơ`),
   chọn mốc kết thúc mới nhất. Hỗ trợ thời gian `HH:mm dd/MM/yyyy` và
   `dd/MM/yyyy HH:mm`, cả lịch sử tăng dần lẫn giảm dần.
3. Ưu tiên dữ liệu cổng cho nhãn, bộ lọc, màu cảnh báo và đối soát. Chỉ dùng XML
   làm phương án dự phòng nếu cổng không có trạng thái. XML gốc vẫn được giữ.

JSON/SQLite lưu `trang_thai_tra_cuu`, `trang_thai_chi_tiet`,
`trang_thai_cap_nhat`; `trang_thai` là giá trị đang có hiệu lực.
“Đã trả kết quả” được giữ nguyên, không đổi thành “Đã tiếp nhận” từ XML.
“Chờ chấp nhận” không được quy thành chấp nhận. Tiêu đề biểu mẫu
“Chấp nhận/Không chấp nhận” không phải quyết định xử lý.

## Kiểm chứng

- Đối chiếu HAR do người dùng cung cấp: truy vấn DVC theo `maHoSo`, xác thực
  tải và tải ZIP. HAR/cookie/dữ liệu hồ sơ thật không được đưa vào repository.
- Kiểm tra trực tiếp một hồ sơ doanh nghiệp được người dùng chỉ định:
  tra cứu và lịch sử chi tiết đều trả “Đã chấp nhận”, chỉ có một XML tiếp nhận.
  Hai lượt tải/cập nhật thành công; lượt sau dùng lại ZIP, SQLite giữ đúng trạng thái.
- Kiểm tra trực tiếp một hồ sơ DVC cá nhân đã có trong kho của tài khoản:
  hai lượt thành công, hai phản hồi XML; lượt sau dùng lại ZIP và giữ trạng thái.
- Kiểm tra cá nhân phát hiện tên kép `01/BĐS - Thông báo doanh thu/Tờ khai thuế`
  từng bị nhận nhầm thành thông báo. ZIP thực chứa XML `HSoThueDTu`; quy tắc
  nhận diện được sửa cho cả tải, kiểm tra và dùng lại tệp, giữ nguyên bộ kiểm tra XML.
- Test tự động dùng HTTP/HTML/XML tổng hợp: đúng bộ lọc cho từng adapter,
  không quét thêm trang, nhận trạng thái theo lịch sử, ưu tiên cổng trên giao diện,
  cập nhật đúng lựa chọn và mở file thông báo bằng ứng dụng mặc định.
- Lượt live dùng thư mục kiểm thử riêng; dữ liệu người dùng đã có không bị di chuyển.
  Adapter cá nhân/doanh nghiệp cũ được kiểm chứng bằng HTTP giả; lượt live
  này kiểm tra DVC cho cả hai loại tài khoản.

Thông báo bản mới đọc GitHub Releases, tự mở nội dung thay đổi, thời gian ở
múi giờ máy và hai nút tải/bỏ qua. Quy tắc phát hiện bản mới vẫn theo phiên bản
ổn định mới hơn; việc thay asset cùng phiên bản không khiến EXE cũ tự nhận là
phiên bản mới. Người dùng tải lại asset 2.1.4 để nhận bản sửa này.

EXE thay lại trong release `desktop-v2.1.4`; manifest ghi commit nguồn build thực,
không đổi tag cũ. GitLab được chuyển thành kho lưu trữ sau khi xác minh bản GitHub.
