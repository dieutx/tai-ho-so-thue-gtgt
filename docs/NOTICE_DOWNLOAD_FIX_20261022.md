# Tải và mở thông báo theo tờ khai — 22/10/2026

Kiểm tra read-only thư mục người dùng cung cấp: 3 ZIP chính hoàn tất; hai hồ
sơ thiếu 4 thông báo, hồ sơ còn lại đã có 2 thông báo hợp lệ. Metadata cũ ghi
`ATTACHMENT_INVALID_OR_SAVE_FAILED`, nên giao diện chỉ báo chung “Chưa đầy đủ”.

Probe có quyền dùng đúng tài khoản đã lưu, chỉ giữ nội dung trong RAM, tái
hiện HTTP 429 tại endpoint tải thông báo. Các POST mặc định không retry vì
không được giả định là thao tác an toàn để lặp; endpoint tải thông báo là
thao tác chỉ đọc và cần được khai báo riêng.

## Bản sửa

- Endpoint downloadthongbao/downloadthongbao-tdt khai báo retry-safe, tối thiểu
  6 lượt tổng cộng: lượt đầu và 5 retry khi HTTP 429. Nếu cấu hình HTTP yêu cầu
  nhiều lượt hơn vẫn được tôn trọng trong budget hữu hạn. Không thay giới hạn
  CAPTCHA/login hay tự retry các POST khác.
- Dùng cơ chế Retry-After/backoff hiện có (trần 60 giây mỗi lần), kiểm tra
  budget và cho hủy trong lúc chờ. Hết retry ghi ATTACHMENT_RATE_LIMITED.
- Giữ PARTIAL khi thông báo còn thiếu dù mọi ZIP chính đã hoàn tất. Tổng kết
  hiển thị số thông báo phát hiện, tải mới, có sẵn, lỗi và lỗi đọc danh sách;
  lỗi được gắn đúng hồ sơ cha, tệp ZIP hợp lệ vẫn được giữ.
- Từng thông báo trong drawer có liên kết Mở thông báo / Mở thư mục chứa tệp.
  Các liên kết là token nội bộ, không thực thi URL lấy từ XML. Tệp bị xóa báo
  rõ, không mở nhầm thư mục hiện hành. Chiều cao dòng đủ hai dòng chữ kể cả
  bố cục nhỏ.

## Kiểm chứng

Test tổng hợp qua HttpClient thật: 5 phản hồi 429 rồi 200 tạo đúng 6 request,
5 lần chờ; 6 phản hồi 429 dừng đúng giới hạn và ghi mã riêng; hủy trong lúc
chờ không gửi request tiếp. Test service kiểm ZIP thành công/không lỗi nhưng
thông báo thất bại vẫn PARTIAL và có lý do theo hồ sơ. Test UI phát tín hiệu
anchorClicked để xác minh mở đúng XML/thư mục và xử lý tệp bị xóa.

Probe source sau sửa đọc lại đúng 4 thông báo đang lỗi: cả 4 giải mã/validate
đạt; dãy HTTP thực tế 200,200,429,200,200 chứng minh một 429 đã chờ/thử lại rồi
thành công. Không lưu XML vào thư mục hồ sơ thật, không sửa metadata người
dùng và không đưa nội dung thuế/credential vào log, Git hoặc fixture.

Người dùng yêu cầu build EXE để tự test; bàn giao candidate riêng sau đầy đủ
source/frozen/OCR/native UI gates. Probe trên là bằng chứng source, không thay
thế kiểm thử online của EXE mới.
