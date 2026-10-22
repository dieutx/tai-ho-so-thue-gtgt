# Changelog

## [2.0.1] — 2026-10-22

Bản phát hành công khai kế tiếp sau 2.0.0; gộp các bản nội bộ 2.0.1–2.0.4 và bộ UX mới.

- Bổ sung giao diện **Phản hồi CQT** dạng bảng con, **XML Viewer** hai chế độ,
  tab **Thông báo thuế** độc lập, xuất **hồ sơ ZIP** có manifest và màn hình
  **Đối soát/Xuất báo cáo**; giữ nguyên hai module Tờ khai/Phản hồi CQT và
  Thông báo thuế.
- Sửa parse bảng: hàng footer/tổng/không có handler được bỏ qua êm; hàng có
  handler nhưng ID lệch vẫn báo lỗi để không giấu thay đổi schema.
- Nhận đúng ZIP thông báo `04/SS-HĐĐT` (XML `<TBao>`), không còn báo nhầm
  "không phải ZIP"; tờ khai vẫn bắt buộc XML declaration.
- Giảm thời gian chờ HTTP 429 từ 15 giây xuống backoff **2s → 4s → 8s**
  (tôn trọng `Retry-After` nếu cổng gửi); dùng lại trang chi tiết/CSRF giữa
  file chính và thông báo để bớt một request mỗi hồ sơ.
- Giữ lưu mật khẩu trong Windows Credential Manager, retry thông báo, định
  danh tài khoản/hồ sơ và các bản sửa 2.0.4.
- Kiểm thử: **855 tests OK (6 skip)**, ruff/mypy pass; tài khoản thật 4/4
  hồ sơ `04/SS-HĐĐT` và 12/12 thông báo trong 14,23 giây.

## [2.0.4] — 2026-10-22

- Tải thông báo DVC khi HTTP 429: cho phép retry riêng thao tác chỉ đọc này,
  chờ Retry-After và thử lại ít nhất 5 lần sau lượt đầu; vẫn chịu timeout,
  budget và hủy an toàn. Không bật retry cho các POST đăng nhập/nghiệp vụ khác.
- Thêm liên kết mở từng thông báo/thư mục ngay trong chi tiết tờ khai; tổng
  kết tách lỗi thông báo khỏi ZIP và chỉ rõ hồ sơ còn thiếu thông báo.

- Rà soát thông báo theo tờ khai: đối chiếu khóa hồ sơ cha/checksum, sửa
  bộ lọc/tìm kiếm, đọc lý do lồng trong XML, giữ trạng thái chưa hiểu là chưa
  xác định; bổ sung sheet tham chiếu thông báo trong báo cáo Excel.
  [Review](docs/NOTICE_REVIEW_20261022.md).

- Tab Tờ khai có cột **Thông báo** đọc trực tiếp XML trong
  `thong-bao-dinh-kem/<mã hồ sơ>/` (tiếp nhận / chấp nhận / không chấp nhận),
  bấm để mở từng tệp; tờ khai bị từ chối được tô đỏ và vào nhóm "Cần kiểm tra".
  Không đọc/ghi mạng, không sửa tệp đã tải.
- Sửa `SCHEMA_CHANGED: REQUIRED_COLUMNS_MISSING_OR_AMBIGUOUS:lan_nop` trên DVC:
  nhận đúng tiêu đề `Lần nộp (Tờ khai)/File số (DLVC)`. Giữ kiểm tra cột bắt buộc,
  cột trùng, thứ tự cột và giá trị lần nộp; không đoán theo vị trí.
- Nhận hàng DVC bỏ ô cuối `Hồ sơ đính kèm` dù vẫn hiện tiêu đề. Chỉ cho phép
  thiếu cột tùy chọn ở cuối hàng; thiếu cột giữa hoặc cột bắt buộc vẫn báo lỗi.
- Smoke Python/EXE thêm bảng DVC tổng hợp với tiêu đề thực tế. Chẩn đoán online
  nhận tùy chọn `dvc` rõ ràng và ghi nguồn hồ sơ để phân biệt DVC với legacy.
- Review các parser còn lại: sửa ETAX bỏ sót bảng khi có nhiều khối cùng CSS,
  ánh xạ thông báo legacy theo tên cột, bỏ text ẩn khi đọc rỗng/phân trang,
  nhận CAPTCHA qua classifier chung và chặn ID GNT xung đột.
  Chi tiết: [SCHEMA_REVIEW_20261022.md](docs/SCHEMA_REVIEW_20261022.md).
- Sửa metadata EXE lấy nhầm phiên bản từ Python đã cài ở checkout cũ; đọc
  phiên bản từ đúng file source, buộc code/metadata/smoke/receipt khớp nhau.
- Nhận phản hồi DVC `status=999` có `desc` xác nhận CAPTCHA sai để thử OCR
  tiếp theo đúng giới hạn; không gán thông điệp lạ hoặc mọi status 999 là CAPTCHA.

## [2.0.3] — 2026-10-21

- Sửa lỗi `NoneType.get` khi trang cổng chứa nhiều phần tử HTML ẩn lồng nhau.
- GNT nhận hai tiêu đề DS chi tiết dài trên cổng thật và dòng tổng tiền theo
  loại tiền ở cuối bảng. Không bỏ qua ô gộp bất thường trong hàng hồ sơ.
- Bấm MST trên thanh đầu để chọn công ty đã lưu; dialog đăng nhập có danh sách
  MST, tự điền mật khẩu và nút quên tài khoản. Chỉ lưu sau đăng nhập thành công
  khi bật “Lưu mật khẩu trên máy này”, bằng Windows Credential Manager; không
  ghi mật khẩu vào settings, log hay file JSON. Đăng xuất xóa phiên hiện tại;
  “Quên tài khoản đã lưu” xóa mật khẩu khỏi Windows Credential Manager.
- Thêm kiểm thử lỗi HTML/GNT và roundtrip kho mật khẩu bằng tài khoản giả vào
  smoke source/EXE. Chẩn đoán online giới hạn hỗ trợ cả tờ khai, GNT, thông báo.

## [2.0.2] — 2026-10-21

- Sửa chặn `DIRECTORY_LEGACY_UNOWNED` sau nâng cấp: desktop tự chọn nhánh
  `tai-moi` của đúng tài khoản khi thư mục cũ chưa có owner manifest. Dữ liệu
  cũ giữ nguyên để mở offline; không tự gán sở hữu hoặc nhận tệp cũ là đã tải.
  Thư mục đã có owner hợp lệ vẫn được dùng lại như trước.
- Thông báo lỗi CLI giải thích đúng giới hạn của công cụ chuyển danh mục.
- Kiểm thử có quyền trên cổng thật phát hiện và sửa alias `Tải thông báo`
  riêng cho bảng tờ khai legacy; chuẩn hóa ngắt dòng trong header thông báo,
  lấy đúng messageId thay vì số tham chiếu hiển thị, nhận namespace XML
  `TBaoThue` riêng. Giữ kiểm tra loại tệp và từ chối namespace chưa hỗ trợ.
- Nhận đúng phản hồi `Mã xác thực không chính xác` để thử lại CAPTCHA hữu hạn;
  không coi chuỗi alert tĩnh hay nội dung XML tờ khai/thông báo là lỗi đăng nhập.
- Chế độ chẩn đoán online opt-in trong EXE dùng Worker/OCR thật, đọc credential
  từ file cấu hình có sẵn; giới hạn ba khoảng ngày 31 ngày, request/thời gian/
  dung lượng, mỗi khoảng tối đa một hồ sơ kèm thông báo. Không chạy khi mở app.

## [2.0.0] — 2026-10-19

- Build local đăng nhập 20/10: nhận diện trang xác minh truy cập HTTP 200;
  không tính lỗi tài khoản/mật khẩu thành 5 lần OCR; bỏ log alert JavaScript
  chưa thực thi; hiển thị đúng nguyên nhân đăng nhập. Giữ phiên bản 2.0.0.
  [Bằng chứng và giới hạn](docs/CAPTCHA_ACCESS_VERIFICATION_20261020.md).
- Build local review 20/10/2026: cập nhật form DSE sau đăng nhập bị từ chối,
  dừng fallback nhập tay bị từ chối thay vì hỏi lặp; dùng đúng form khi cổng đổi
  tên; kiểm tra lại nguồn XML và bắt buộc OCR source/EXE khớp. 476 test/6 skip,
  native UI 18/18 và frozen offline/OCR đạt. Giữ 2.0.0; chưa thay asset công khai.
  [Review và hash bản local](docs/DEEP_REVIEW_20261020.md).
- Cập nhật lại asset 2.0.0: tự thử CAPTCHA tối đa 5 lần với ảnh mới khi phải thử
  lại, sau đó mới thông báo và cho nhập tay. Hiển thị tiến độ OCR; thành công
  đặt lại bộ đếm. Model OCR giữ nguyên như Python. Không tạo phiên bản mới.
- Giao diện mới: chọn kỳ nhanh, lọc và chọn nhiều hồ sơ, khung chi tiết,
  lịch sử tải, xuất danh sách Excel; có ảnh UI mới và hướng dẫn ngắn trong README.
- Tách trạng thái thuế/trạng thái tệp; kiểm tra tệp đã có, tải phần chưa có hoặc
  thử lại lỗi. Tra cứu không tạo dữ liệu đầu ra; chỉ tải đúng hồ sơ đã chọn.
- Sửa trang chuyển tiếp/redirect/form legacy cho GNT và thông báo; giới hạn
  đăng nhập lại một lần, báo lỗi HTTP rõ thay vì lặp tra cứu rỗng.
- Sửa xử lý quyền ghi/OneDrive/tệp khóa/hết đĩa, giữ tệp đã tải xong.
- DVC mặc định bật; ETAX dùng chung phiên, DVC tách cookie; offline không mạng.
- Full EXE 88,323,106 B, OCR tự động; 467 test tổng/6 skip, native UI 18/18,
  frozen offline/OCR hai lượt PASS. [Nghiệm thu](docs/DESKTOP_ACCEPTANCE.md).

## [1.1.0] — 2026-10-19

- Desktop bật DVC mặc định; CLI giữ mặc định cũ. DVC lỗi không làm mất kết quả
  ETAX khi tra cứu qua cutoff. Cookie hai cổng tách biệt.
- Giao diện thêm màu theo thao tác, hướng dẫn khi trống, footer lỗi ngắn có
  liên kết nhật ký; giữ bảng luôn hiện ở màn hình thấp. Ngày mặc định là tháng trước.
- Thêm thông tin phiên bản/build, ghi chú thay đổi và kiểm tra GitLab public
  releases theo nút bấm. Không tự tải/cài và không gửi thông tin thuế.
- Retry hữu hạn lỗi khóa tệp Windows 5/32/33; báo hướng khắc phục lỗi ghi danh
  mục, giữ kết quả/tệp đã tải. Mặc định tránh Documents chuyển vào OneDrive.
- CAPTCHA OCR bị từ chối chuyển sang nhập tay; hiển thị `Đã có hợp lệ` khi reuse.
- Thêm tải nhiều nhóm tuần tự, mở/chuyển dữ liệu cũ không cần đăng nhập.
- Build từ venv runtime mới, tách công cụ kiểm tra; thêm qjpeg cho CAPTCHA JPEG,
  metadata phiên bản 1.1.0.0, ma trận UI đủ 15 cấu hình.
- Kiểm thử dữ liệu thật: tải 5 hồ sơ DVC, 52 GNT và 5 thông báo; chạy lại giữ
  hash; khoảng thông báo 01/06–01/07/2025 trả 2 bản ghi. Không đưa hồ sơ thật vào EXE.
- Số đo cuối, hash, kiểm thử và giới hạn: [nghiệm thu](docs/DESKTOP_ACCEPTANCE.md),
  [dung lượng](docs/BUILD_SIZE_REPORT.md).

## [1.0.0] — 2026-10-19

Bản desktop compact, một tài khoản/một phiên ETAX và Full EXE nhẹ hơn. Số
version trong EXE vẫn là 1.0.0; đây là bản phát hành desktop của mốc này.

### Thêm

- `desktop` (PySide6): bốn nghiệp vụ Tờ khai, Giấy nộp tiền, Thông báo thuế và
  Phân tích XML, gọi pipeline Python in-process thay vì spawn CLI.
- `ETaxSessionManager` dùng chung `requests.Session` + DSE/home state cho ba
  nghiệp vụ ETAX legacy; DVC có client/cookie riêng; Offline không tạo client.
- Một dialog tài khoản ở header; mật khẩu masked, chỉ tồn tại trong bộ nhớ,
  không lưu vào settings/log/argv.
- RunHooks tùy chọn cho tiến độ/cancellation; `Dừng an toàn` không kill thread.
- Dialog CAPTCHA thủ công hoạt động ở bản `--windowed`, không dùng stdin.
- Settings/log có redaction; output mặc định theo Known Folder, chọn được thư mục.
- Màn hình compact: ngày/nơi lưu dùng chung, state riêng từng tab, footer một
  hàng, empty state, bảng cuộn nội bộ; hỗ trợ 1024×600 và DPI 100–150%.

### Sửa

- Không còn đăng nhập lại khi chuyển tab hoặc chạy lần lượt Tờ khai → GNT →
  Thông báo; test xác minh login chỉ một lần và 0 login khi đổi tab.
- Phiên hết hạn được invalidate và relogin tối đa một lần, không loop; đổi tài
  khoản xóa cookie/state cũ.
- Không báo `Thành công` cho kết quả rỗng, lỗi, DVC bị tắt hoặc báo cáo chưa tạo;
  cutoff DVC trả `PARTIAL`/thiếu dữ liệu đúng nghĩa.
- Test UI kiểm tra control thực sự hiển thị (tab hoặc combo) thay vì widget ẩn.

### Đóng gói

- Full EXE onefile/windowed: **202.938.102 → 88.136.033 byte** (−56,6%),
  OneDir **410.887.557 → 223.147.429 byte** (−45,7%), vẫn có OCR tự động.
- Chỉ đóng gói model mặc định `ddddocr/common_old.onnx`; loại model beta và
  detection không được desktop dùng.
- Loại FFmpeg video backend, `PIL._avif/_webp`, opengl32sw, Qt
  Quick/Qml/Pdf/OpenGL/Network/SVG/VirtualKeyboard, translations và plugin
  không dùng; giữ `qwindows.dll`, Qt core/GUI/Widgets, cv2, ONNX CPU, numpy.
- `requirements-desktop.txt` chuyển sang pin runtime CPython 3.11, bỏ `-e .[dev]`;
  spec có chế độ onedir để đo nội tạng, audit archive và frozen smoke tự động.
- SHA-256 bản bàn giao:
  `605d94dabdd755ebbb9c3e6ef215019c2a6fe91bda0148ebd5b1ee08d77e906d`.

### Kiểm thử

- 421 test pass, 6 skip (OCR tùy chọn); ruff pass; mypy `gdt_tax` pass.
- Frozen self-test hai lượt trong thư mục Unicode chỉ có EXE: offline + mapping +
  OCR, socket bị chặn; GUI native và 10 cấu hình UI/DPI pass.
- Audit: 158 archive entry, 0 đường dẫn cấm, 0 secret khớp, 1 model ONNX.

### Giới hạn

- Chưa kiểm chứng trên VM Windows sạch, tài khoản thuế thật, DVC live, RDP hoặc
  đổi màn hình/DPI vật lý.
- Bản Full không kèm model beta của ddddocr; cần beta thì chạy từ source.
- Chưa build bản Lite (CAPTCHA nhập tay), chưa thử UPX, EXE chưa ký số.
