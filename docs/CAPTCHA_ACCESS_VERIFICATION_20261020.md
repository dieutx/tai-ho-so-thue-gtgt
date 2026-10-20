# Phân biệt CAPTCHA đăng nhập và xác minh truy cập — 20/10/2026

Tiếp tục sau khi người dùng chạy EXE mới và vẫn gặp 5 lượt tự động, rồi lượt
nhập tay bị từ chối. Người dùng xác nhận đang dùng tài khoản khác với `.env`.
Kết quả đăng nhập thành công bằng `.env` trước đó không xác minh tài khoản này.

## Bằng chứng mới

Đã kiểm tra đăng nhập bằng thông tin người dùng cung cấp trong phiên, không tải
hồ sơ. Không ghi thông tin đó vào mã nguồn, `.env`, tài liệu hoặc đối số tiến trình.

Trong lần tái hiện, POST có đầy đủ tài khoản, mật khẩu và CAPTCHA; dữ liệu của
request thực tế khớp dữ liệu đầu vào. Máy chủ trả **HTTP 200 nhưng là trang xác
minh người truy cập**, có câu hỏi human visitor, ô `answer` và nút Submit, không
có form đăng nhập ETAX hoặc dấu hiệu chuyển sang trang chủ.

Code cũ coi mọi phản hồi không có marker thành công là một lần CAPTCHA thất
bại. Do đó trang xác minh này cũng bị đếm vào 5 lần OCR và dẫn tới hỏi CAPTCHA
đăng nhập bằng tay. Thêm model OCR không xử lý được việc phân loại phản hồi sai.

Ba câu “chưa nhập tên đăng nhập/mật khẩu/mã xác nhận” được đọc từ các lệnh
`alert()` bên trong hàm kiểm tra JavaScript, không chứng minh rằng request gửi
thiếu trường. Đã kiểm tra mã form thật: đăng nhập gọi native `form.submit()`.

Sau đó đối chiếu bằng Playwright với Edge trong phiên trình duyệt riêng:
đã đi qua trang Doanh nghiệp → tài khoản Thuế điện tử → form đăng nhập thật.
Một lượt OCR trên ảnh chụp bị thu nhỏ nhận lỗi “Mã xác thực không chính xác”.
Lượt với ảnh kích thước gốc và mã đọc rõ nhận thông báo từ cổng:
“Tên đăng nhập hoặc mật khẩu của bạn không chính xác!”. Đây là thông báo hiển
thị trong trang trả về, khác với các chuỗi JavaScript tĩnh ở trên.

Người dùng đã sửa lại mật khẩu trong phiên. Kiểm tra lại bằng mã ứng dụng,
giữ nguyên tên đăng nhập và OCR mặc định, **đã đăng nhập thành công**: POST
HTTP 200 có luồng `corporateHomeProc`, không còn form đăng nhập, mở được trang
chủ và hoàn tất `portal.login()`. Không tải hồ sơ. Trong trình duyệt, thông tin
mới đi tới trang yêu cầu công cụ ký điện tử; không cài tiện ích hoặc công cụ ký.
Không suy ra mọi lần gặp lỗi trước đó đều do cùng một nguyên nhân.

Kiểm tra tiếp bằng đúng `Worker` → `GuiCaptchaSolver` → `ETaxSessionManager`
của desktop source cũng trả `SUCCESS`, phiên đã xác thực, không yêu cầu CAPTCHA
tay và không tải tệp. Không đổi chữ hoa/thường của tên đăng nhập hoặc mã OCR
trong phép thử này. Không thêm Playwright vào dependency hoặc EXE của ứng dụng.

Phản hồi thực tế chỉ lưu trong cache riêng để chẩn đoán. Không đưa HTML, ảnh
xác minh, support ID, thông tin tài khoản/mật khẩu vào bằng chứng phát hành.

## Sửa

- Nhận diện trang xác minh truy cập ở HTTP client, gồm HTTP 200; dừng trước các
  vòng retry đăng nhập/tra cứu. Không đếm trường hợp này thành lỗi nhận dạng OCR.
- Báo lý do xác minh trình duyệt trực tiếp trong hộp lỗi đăng nhập, không che
  bằng thông báo tài khoản/mật khẩu/CAPTCHA chung. Hộp lỗi hiển thị plain text.
- Bỏ việc ghi các chuỗi alert JavaScript chưa thực thi vào nhật ký đăng nhập.
- Khi phản hồi hiển thị lỗi tài khoản/mật khẩu đã biết, dừng ngay sau một
  request và báo đúng lý do; không gọi OCR rejected hoặc chuyển sang nhập tay.
  Chuỗi lỗi nằm trong JavaScript chưa thực thi không kích hoạt nhánh này.
- POST login dùng header điều hướng document/navigate, khớp native form trên
  website; các nghiệp vụ AJAX vẫn giữ kiểu XHR. Giữ nguyên tên đăng nhập đã nhập.
- Kiểm tra phần tử form thật khi nhận diện trang đăng nhập/thành công; một
  biến JavaScript chứa chuỗi `loginForm` không còn làm bỏ sót trang thành công.
- Frozen self-test bắt buộc nhận diện trang xác minh, cùng các kiểm tra OCR và
  fallback trước đó. Không đổi mô hình hoặc runtime; giữ phiên bản 2.0.0.

## Kiểm chứng

- Bộ nhận diện đã phân loại đúng phản hồi xác minh thực tế vừa nhận, đồng thời
  cho qua phản hồi đăng nhập thành công của tài khoản `.env` đã lưu trước đó.
- Regression dùng HTML tổng hợp: dừng ngay HTTP 200/403, không lặp request hoặc
  tính lỗi OCR; không nhầm script/noscript của trang bình thường với xác minh;
  header login đúng; không log alert tĩnh; UI hiển thị nguyên nhân cụ thể.
- 486 test: 480 đạt, 6 bỏ qua; ruff đạt; mypy đạt cho 66 module core.
- EXE: 18/18 cấu hình giao diện đạt; hai lượt frozen offline đạt; hash ảnh,
  kết quả OCR, model và charset khớp source; nhận diện trang xác minh đạt.
  Bundle audit đạt, không thiếu module OCR hoặc DLL ONNX cần thiết.
- EXE local 2.0.0: **88.328.668 byte**, SHA-256
  `d710acb31993d41dc24b8d28e0fdb35520730d0536a610c9e96df2727062c85c`.
- Bằng chứng đóng gói, parity OCR source/EXE và kiểm tra giao diện:
  [tổng kết](desktop-evidence/2.0/access-verification-20261020/review-summary.json).

Chưa chứng minh được vì sao hệ thống bảo vệ yêu cầu xác minh đối với lần truy
cập HTTP trước đó. Đăng nhập thành công ở trên là kiểm tra online bằng source;
EXE được kiểm tra offline và đối chiếu OCR với source, chưa kiểm tra đăng nhập
online trực tiếp trong cửa sổ EXE. Không tự vượt qua trang xác minh truy cập.
Báo cáo này chốt ở thời điểm build local trong `dist`. Trạng thái phát hành
sau đó và source commit tương ứng được ghi trong ghi chú Release 2.0.0 trên GitLab.
