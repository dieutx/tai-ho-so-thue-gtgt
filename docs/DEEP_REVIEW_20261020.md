# Review và build lại desktop 2.0.0 — 20/10/2026

Build trong báo cáo này đã được thay bằng
[bản sửa phân biệt lỗi đăng nhập/xác minh truy cập](CAPTCHA_ACCESS_VERIFICATION_20261020.md).
Các hash và số đo bên dưới thuộc build review trước đó.

Review theo phản ánh EXE trong `dist` mở nhập CAPTCHA liên tục, luôn nhắc đã thử
5 lần. Giữ phiên bản 2.0.0. Chưa xác định được nguyên nhân của đúng lần đăng nhập
người dùng gặp lỗi; các lỗi có thể tái hiện dưới đây đã được sửa và kiểm thử.

## Phạm vi

- Entrypoint, tài khoản/cấu hình GUI, Worker/QThread, hủy tác vụ, OCR và nhập tay.
- Đăng nhập ETAX/DVC, trạng thái DSE, cookie riêng giữa nguồn, thử lại khi hết phiên.
- Form tra cứu, phân trang và tải tờ khai/GNT/thông báo; lưu, tiếp tục và metadata.
- Kiểm kê ZIP/XML, đọc manifest, mapping, provenance, phân loại và xuất Excel.
- Spec/dependency, nội dung bundle, mô hình/DLL, dữ liệu bí mật và smoke EXE độc lập.

## Phát hiện và sửa

| Mức | Lỗi xác minh được | Sửa và kiểm chứng |
|---|---|---|
| Cao | Legacy gửi lại trường ẩn và Referer của form đăng nhập đầu tiên sau khi cổng trả form mới. Nếu trạng thái form đổi, các lượt sau dùng thông tin cũ. | Dùng form mới cho ảnh/POST tiếp theo. Regression mô phỏng thay `dse_pageId` và URL sau lần đầu bị từ chối; trước sửa gửi `old, old`, sau sửa gửi `old, new`. |
| Vừa | Sau 5 lỗi tự động, mọi lượt retry còn lại đều hỏi nhập tay với thông báo 5 lần cũ. Một lượt nhập tay bị từ chối không kết thúc fallback. | Chỉ hỏi nhập tay một lượt sau 5 lượt tự động. Khi chưa được xác nhận, kết thúc với thông báo kiểm tra mã/tài khoản/kết nối. Thành công reset OCR. Chế độ manual được chọn riêng giữ nguyên. Regression kiểm tra cả legacy và DVC; frozen self-test kiểm tra bộ đếm và reset. |
| Vừa | Bộ dò form chỉ kiểm tra tên form xuất hiện trong HTML, nên có thể chọn tên trong script dù form thực tế mang tên khác. | Kiểm tra phần tử `form` thật theo `id`/`name`, sau đó đối chiếu operation. Regression có tên cũ trong script và form mới trong DOM. |
| Vừa | Tra cứu tờ khai kiểm tra tên form cố định; tải thông báo cũng POST theo tên cố định sau khi đã nhận form mới. | Cập nhật và dùng tên form thực tế xuyên suốt tra cứu, phân trang và tải. Regression kiểm tra tra cứu lặp lại/tải trên form đổi tên. |
| Cao | Parser đọc lại tệp sau kiểm kê nhưng giữ SHA-256 cũ mà không so bytes; tệp mất/không đọc được bị bỏ qua. Bước đọc lại chưa giới hạn đường dẫn/kích thước như inventory. | So hash trước parse, báo dòng `error` khi nguồn đổi/mất; yêu cầu kiểm kê lại. Chặn đường dẫn ngoài thư mục nguồn và giới hạn đọc XML/member ZIP. Regression kiểm tra nguồn đổi/mất, đường dẫn ngoài nguồn, XML/ZIP vượt giới hạn. |
| Vừa | Audit chỉ đếm model; thiếu model/DLL/bảng ký tự không tự làm audit thất bại. Smoke chưa bắt buộc source/EXE trả cùng kết quả. | Audit bắt buộc model đúng hash, DLL và các module nạp OCR/bảng ký tự. Smoke so hash ảnh, kết quả, model, charset và execution provider giữa source/EXE. Regression audit bỏ model/DLL/charset và thay bytes model. |
| Thấp | GUI che mất loại exception OCR và không ghi rõ trường hợp kết quả rỗng. | Ghi loại exception hoặc kết quả rỗng/sai độ dài, không ghi nội dung exception có thể chứa dữ liệu riêng. Thông báo cổng từ chối yêu cầu không khẳng định chắc chắn OCR đọc sai. |

## Giả thuyết thiếu model

EXE trước sửa có model `ddddocr/common_old.onnx`, 13.606.051 byte, SHA-256
`b8f2ad9cbc1f2e3922a6cb9459e30824e7e2467f3fb4fd61420640e34ea0bf68`, đúng với
model Python. Đã kiểm tra DLL ONNX và các module OCR/charset bên trong archive.

`DdddOcr(beta=False)` chỉ nạp model này. `common.onnx` dùng cho beta;
`common_det.onnx` dùng cho phát hiện vùng ảnh. Hai model đó không tham gia luồng
desktop hiện tại. Không thay model hoặc pin ONNX chỉ theo phỏng đoán.

Chạy lại chính EXE trước sửa trên ba ảnh đã lưu: kết quả OCR khớp Python cả ba.
Worker Python với cấu hình đã cho phép kiểm tra đăng nhập ETAX và tra cứu DVC
thành công; không mở nhập tay. Các dữ liệu/ảnh thực tế chỉ nằm trong cache riêng,
không đưa vào tài liệu hoặc bundle.

## Kiểm chứng bản build mới

- EXE local: `dist/TaiHoSoThue-Windows.exe`, **88.326.543 byte**, phiên bản **2.0.0**.
- SHA-256: `cfaf74f24e232b08884e13942fb38079bc98d326e36de338802e41bbe9282ee2`.
- **476 test: 470 đạt, 6 bỏ qua**, không thất bại. Các ca bỏ qua thuộc backend tùy chọn.
- Ruff đạt; mypy core đạt (65 module).
- Audit bundle đạt: không có dữ liệu/thư mục cấm hoặc giá trị bí mật khớp kiểm tra;
  model đúng hash, đủ DLL và module OCR/charset.
- Hai lượt EXE độc lập, không sidecar, đường dẫn có dấu/khoảng trắng: offline/OCR
  và kiểm tra fallback đạt; ảnh/kết quả/model/charset/provider khớp source.
- Chạy tiếp EXE mới trên ba ảnh CAPTCHA đã lưu: cùng ảnh và cùng kết quả OCR
  với Python cả ba; không đưa ảnh hoặc nội dung mã vào bằng chứng công khai.
- **18/18 cấu hình native UI/DPI đạt**. Đã xem ảnh 1920×1040 và 1024×560 ở 150%.
- Worker source sau sửa: đăng nhập ETAX và tra cứu DVC đạt; 4 lượt OCR, không
  exception OCR, không yêu cầu nhập tay. Không tải hồ sơ trong lượt kiểm tra này.
- File checksum local đã cập nhật. Đây là build local; chưa thay asset công khai.

[Tổng kết và hash](desktop-evidence/2.0/deep-review-20261020/review-summary.json),
[audit](desktop-evidence/2.0/deep-review-20261020/bundle-audit.json),
[source](desktop-evidence/2.0/deep-review-20261020/source-report.json),
[EXE lượt 1](desktop-evidence/2.0/deep-review-20261020/report-1.json),
[EXE lượt 2](desktop-evidence/2.0/deep-review-20261020/report-2.json).

Không coi kiểm thử offline hoặc Worker chẩn đoán là bằng chứng đã tái hiện toàn
bộ thao tác UI/tài khoản của lần người dùng gặp lỗi. Bản sửa form đăng nhập được
kiểm chứng bằng mô phỏng cổng đổi trạng thái sau lần từ chối; chưa chứng minh đó
là nguyên nhân của đúng phiên lỗi đã được phản ánh. Giữ nguyên model và runtime.
