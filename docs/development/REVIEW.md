# Rà soát logic và hướng mở rộng

Ngày rà soát: 27/09/2026. Ban đầu kiểm tra mã nguồn, fixture và test offline.
Sau đó đã chạy test thật qua legacy bằng cấu hình `.env` theo yêu cầu người
dùng, rồi chạy lại để kiểm tra resume. Không kiểm chứng lại endpoint DVC.
Tài liệu chỉ ghi số liệu và tên mẫu chung; không chứa credentials/hồ sơ thật.
Trước commit, đã thay tên tài khoản cố định trong bốn test liên quan bằng
`synthetic-taxpayer-QL` và kiểm tra file thay đổi không chứa giá trị tài khoản,
mật khẩu hay proxy trong `.env`. Đây không phải công cụ quét bí mật toàn bộ lịch sử Git.

## Những điểm đã sửa

| Vấn đề trong repo trước thay đổi | Hậu quả | Điều chỉnh |
|---|---|---|
| Pipeline luôn login DVC, ETAX là nguồn trước cutoff; legacy chỉ sau lỗi tải | Legacy phụ thuộc DVC; không đúng chính sách mới | Legacy trực tiếp mặc định, DVC tắt qua feature flag; login DVC chỉ khi có đoạn DVC/ETAX được bật |
| Phần DVC bị tắt chưa có biểu diễn kết quả | Dễ hiểu nhầm đã tải đủ khoảng ngày | `skipped_periods`, warning ghi từng khoảng; mã thoát 1 cả dry-run |
| Ngày mặc định cố định trong tháng 09/2026 | Mặc định không còn phù hợp với nguồn đang bật | Ngày mặc định nằm trong tháng chứa ngày trước cutoff; env/CLI vẫn ưu tiên |
| Tìm ZIP bằng `*ma_ho_so*.zip` | Mã `123` nhận nhầm file `9123` hoặc `1234` | Dò mã ở đầu tên, có ranh giới; giữ hỗ trợ tên cũ |
| Kiểm tra file có sẵn trước dry-run | Dry-run có thể đổi tên ZIP và tăng số đã tải | Kiểm tra dry-run trước storage |
| Gặp case-id thì dừng dù tải lỗi | Không thử lại bản ghi ở đoạn sau | Chỉ dừng khi tải thành công hoặc đã tìm thấy trong dry-run |
| Tổng trang có nhưng trang tiếp theo lặp/rỗng | Báo thành công dù chưa biết có thiếu dữ liệu | Báo SearchError; kết quả đã lưu vẫn giữ lại |
| Legacy rỗng không có bảng/pagination | Coi khoảng hợp lệ không có hồ sơ là lỗi CAPTCHA | Nhận thông báo rỗng cụ thể + form; trả tổng trang 0 |
| Legacy thay form tra cứu bằng HTML lỗi HTTP 200 | Lần retry sau không còn form hợp lệ | Chỉ cập nhật trạng thái sau khi nhận kết quả nhận diện được |
| Đóng gói mọi body không có MIME text/html thành ZIP | HTML MIME sai/XML hỏng được tính là tải xong | Kiểm tra XML well-formed, chặn HTML và DTD; không giải entity, không đọc mạng |
| Header Origin legacy chứa `/etaxnnt` | Origin không đúng dạng scheme + host | Dùng `LEGACY_ETAX_ORIGIN` |
| Metadata ghi đè danh sách mỗi lần chạy; ghi file trực tiếp | Mất danh sách khoảng trước, có thể có file dang dở | Gộp JSON theo nguồn/mã hồ sơ; ghi từng file bằng temp + replace; từ chối ghi đè JSON hỏng |
| Chưa có báo cáo Excel theo danh sách tờ khai | Người dùng phải tự chuyển metadata | Xuất Excel 11 cột từ danh mục đã gộp; filter/freeze header, chống formula injection |
| Số retry/timeout <=0, pause âm/NaN/Inf được nhận | Vòng retry không chạy hoặc sleep lỗi | Validate ngay khi đọc cấu hình |
| Thiếu `_password`, DSE fields trong bộ che log | Request legacy có thể lộ mật khẩu/trạng thái phiên ở dữ liệu có cấu trúc | Bổ sung tên trường; vấn đề raw response/URL vẫn cần stage 01 |
| CLI để file log mở sau khi main trả về | Test Windows và ứng dụng nhúng không dọn được file | Đóng handler thuộc CLI trong finally; test đóng handler trước cleanup |

## Kiểm kê artifact và discovery (stage 02)

Đã thêm `gdt_tax/inventory.py` và `tests/test_inventory.py`. Công cụ offline, chỉ
đọc: quét đệ quy ZIP/member, SHA-256, nhận diện định dạng từ bytes, profile cấu
trúc XML, dựng manifest + báo cáo discovery. Không trích xuất chỉ tiêu, không
sửa file nguồn.

Chạy trên `download/` (02/10/2026): 1262 file, 1268 member (1265 XML, 3 PDF),
96 `structure_signature` / 92 `structure_skeleton`, 32 mã mẫu, 31 phiên bản,
6 giá trị trạng thái tiếp nhận. Toàn bộ XML parse được (`ok`), 0 lỗi.

An toàn đã có test: Zip Slip/`..`, ZIP hỏng, member mã hóa, member quá lớn, tỉ lệ
nén bất thường, XML UTF-16/BOM, XML lỗi, giới hạn depth. Chạy lại dùng cache
theo `(rel_path, size, mtime)` — nhanh hơn nhiều so với băm lại.

Giới hạn còn lại (thuộc stage 02–03):

* Chưa nối ZIP với hồ sơ khi tên file không khớp `danh_sach_ho_so.json`
  (661/1262 container không khớp vì tên ZIP trong thư mục không còn đúng quy ước
  metadata, ví dụ bản tải lại/đổi tên).
* `possible_tax_type` chỉ suy từ tên mẫu; chưa phải phân loại nội dung.
* `MULTIPLE_STRUCTURES` xuất hiện khi cùng form/version có nhiều skeleton; cần
  người dùng xác nhận đâu là biến thể thật trước khi build mapping.
* Chưa có role tài liệu (tờ khai/phụ lục/thông báo) theo nội dung và chưa có
  parser chỉ tiêu.

## Khung parser tờ khai (stage 04)

Đã thêm `gdt_tax/parser/` (models, xml_reader, registry, extract, cli) và
`tests/test_parser.py`. Khung tách parsing engine khỏi mapping: registry nạp
`gdt_tax/form_mappings/*.json`, extractor lấy chỉ tiêu tổng hợp từ `CTieuTKhaiChinh`,
không hard-code mẫu biểu.

Chạy trên `download/` (02/10/2026): 1265 tờ khai parse được, 0 lỗi, 53 cặp
form/version.

Ba mapping dựng từ logic VBA người dùng cung cấp, tên chỉ tiêu đối chiếu thông tư:
`gtgt_842_01-gtgt` (01/GTGT, 27 chỉ tiêu), `tncn_864_05kk-tt80` (05/KK-TNCN
TT80, `ct16`…`ct32`), `tncn_394_05kk-tt92` (05/KK-TNCN TT92, `ct21`…`ct36`).
Sau khi thêm 03/TNDN: **479/1265 tờ khai `MAPPED`** (842: 245, 864: 138,
394: 76, 892: 20), phần còn lại `NEED_MAPPING`. Mapping 842/864/394 khai
`form_version=null`; 892 tách chính xác 2.5.1 và 2.9.4 vì cấu trúc C7 khác nhau.

Điểm quan trọng: **hai bản TNCN giữ riêng**, không gộp chỉ tiêu — mã `[21]`… trùng
số nhưng khác ý nghĩa giữa TT80 và TT92 (có test `test_same_code_number_different_meaning`).
Chỉ tiêu không có trong mapping (vd `ct21` cờ "không phát sinh" của 842, `ct15`
của 864) vẫn `NEED_MAPPING`, không tự gán. Đây là hành vi có chủ đích (spec §3.1, §45).

Mẫu **02/KK-TNCN (TT156)** chưa làm vì không có XML nào trong thư mục để xác minh
XPath; không bịa. 03/TNDN 892 đã có fixture ẩn danh cho cả chính thức/bổ sung,
giữ kỳ năm tài chính và không lấy BCTC/phụ lục. Các mẫu còn lại (quyết toán
TNCN 953, …) chưa có mapping.

Đã có test: trích metadata chung, chỉ tiêu + provenance XPath, phân biệt NULL/0,
giữ số âm, không lấy bảng kê chi tiết, mapping theo registry, **không tự áp
mapping cho version khác**, XML không namespace, XML lỗi vẫn giữ source reference,
chuẩn hóa số Việt/Mỹ, nạp mapping lỗi bị bỏ qua.

Giới hạn còn lại:

* Có năm mapping cho 842/864/394 và 892 v2.5.1/v2.9.4; mẫu khác giữ `NEED_MAPPING`.
* Phân loại nội dung đã có nhưng chưa nhận diện đầy đủ vai trò phụ lục theo marker;
  tờ khai thông báo (`TBao`) không có `CTieuTKhaiChinh` nên 0 chỉ tiêu.
* Chưa gộp nhiều lần nộp cùng kỳ, chưa tính `declaration_family_id` và chưa nối
  acceptance status cho mọi file không khớp metadata. Excel hiện giữ mọi lần nộp.

## Phân loại nội dung và xuất báo cáo (stage 03 + 08)

Đã thêm `gdt_tax/classify.py` + `tests/test_classify.py` (phân loại từng artifact
theo nội dung XML: nhóm thuế, vai trò, bằng chứng, conflict/unknown) và
`gdt_tax/export.py` + `tests/test_export.py` (ghép manifest+parsed+classification,
lọc, xuất Excel 11 sheet + CSV + audit log).

Chạy trên `download/` (02/10/2026): 1265 artifact phân loại (OK=776, UNKNOWN=489,
CONFLICT=0); workbook `Tax_Return_Summary.xlsx` 11 sheet, `01_RETURN_INDEX` 1265
dòng, `05_INDICATORS` 26282 dòng chỉ tiêu (kèm XPath).

Điểm đã kiểm bằng test: `record_id` ổn định theo hash (không phải số thứ tự);
lọc không làm mất lịch sử; NULL khác 0; **tiền âm giữ nguyên dạng số** (chỉ escape
chuỗi bắt đầu `=,+,-,@` không phải số); CSV UTF-8 BOM; sheet đúng tên.

Giới hạn còn lại:

* `classify.py` chưa tách `APPENDIX` theo marker `PLuc`/`BangKe` (đang suy từ root).
* Chưa có mapping quyết toán TNCN (953) — cần logic XPath như các mapping đã có;
  các tờ khai đó vẫn `NEED_MAPPING` nhưng vẫn xuất được index.
* Chưa đo benchmark thời gian/RAM (stage 08 mô tả) và chưa hỗ trợ SQLite.

## Nền tảng phân loại đã có

`classification.py` là rule thuần, dùng tên tờ khai và TTHC để phân nhóm GTGT,
TNCN, TNDN, OTHER, UNKNOWN. `loai_to_khai` cũ vẫn có nghĩa chính thức/bổ sung;
không dùng trường đó làm nhóm thuế. Phân loại còn tách DECLARATION, NOTICE,
APPENDIX, UNKNOWN. Tín hiệu nhiều nhóm được giữ UNKNOWN kèm lý do.

Rule có phiên bản `metadata-keyword-v1`. CSV/JSON có nhóm, loại tài liệu và lý
do; `phan_loai_ho_so.json` nhóm các hồ sơ có `tep_zip`. Không chuyển/giải nén file
cũ. Một nhóm ở cấp hồ sơ chưa chứng minh mọi file trong ZIP thuộc nhóm đó.
`parsing.py` chỉ parse bảng HTML; parser XML nằm riêng trong `gdt_tax/parser/`.

## Việc cần ưu tiên tiếp

| Ưu tiên | Điểm còn lại | Hướng xử lý / stage |
|---|---|---|
| P1 | Raw response/body dump và URL/Referer có thể chứa dữ liệu phiên, thông tin thuế; che dict không đủ | Redact có cấu trúc + tài liệu phân biệt dump thô/dump chia sẻ, stage 01; hiện coi dump là dữ liệu riêng tư |
| P1 | `valid_zip()` đọc/decompress không có giới hạn; XML legacy cũng chưa giới hạn bytes | Giới hạn dung lượng, số member, tỉ lệ nén, XML bytes/depth; stage 01–02 |
| P1 | Lỗi mạng/hết phiên có thể dừng cả run; DVC bật trở lại vẫn login trước phần legacy | Lazy auth từng nguồn, retry có giới hạn, checkpoint/trạng thái lỗi; stage 01 và 09 |
| P1 | Resume dựa trên tên/ZIP nguyên vẹn, chưa có hash/provenance theo tài khoản và source | `CaseIdentity` + artifact hash, manifest versioned; stage 01–02; hiện dùng thư mục riêng mỗi tài khoản |
| P1 | Tên cũ dạng `<id>-ten.zip` có thể mơ hồ với mã cũng chứa `-`; records/succeeded trong run chỉ dùng mã | Dò manifest theo identity trước tên file; migration không tự gán file mơ hồ, stage 01–02 |
| P1 | Chưa có mẫu XML đại diện để biết mã mẫu, phiên bản, chỉ tiêu | Fixture ẩn danh, inventory và schema matrix trước viết parser, stage 02–07 |
| P2 | Config `pick()` đánh giá env trước override; env sai kiểu có thể chặn CLI override hợp lệ | Đọc lazy theo đúng ưu tiên, kiểm tra `max_days<=31`, capability page size legacy; stage 01 |
| P2 | HTTP chỉ retry 429, Retry-After mới đọc dạng số, không có trần chờ | Chính sách theo loại request, đọc HTTP-date, backoff trần/cancellation; stage 01 |
| P2 | Ghi toàn bộ metadata sau từng hồ sơ; bốn file không có transaction chung | JSON là danh mục chính hiện tại; snapshot theo trang hoặc SQLite/manifest journal sau benchmark, stage 01/08 |
| P2 | Parse HTML theo chỉ số cột, marker/form đơn giản; chưa phát hiện mọi biến thể layout | Validate headers/schema HTML, fixture layout thay đổi, stage 01/09 |
| P2 | Chưa phân loại file đính kèm, chưa biết form/schema từ nội dung | Inventory một Case → nhiều Artifact, rồi classifier độc lập, stage 02–03 |

Không cần thêm framework lớn hay database ngay. Tách các ranh giới Case,
Artifact, Classification, ParsedDeclaration trước; chỉ đổi cách lưu khi có số
liệu về dung lượng, thời gian và nhu cầu truy vấn.

## Cách xác minh

Baseline trước sửa: 269 test, 8 skip cho backend OCR chưa cài, 4 lỗi đóng log
trên Windows. Lint và mypy của baseline qua. Kiểm tra sau sửa theo ba lệnh CI:

```powershell
python -m unittest discover -s tests -t . -v
ruff check .
mypy gdt_tax
```

Kết quả nền tảng trước đây: 297 test OK trên Windows. Sau inventory/parser/
classify/export và sửa vòng lặp tự quét workbook đầu ra, kiểm tra ngày 02/10/2026
có 347 test OK, 6 skip backend OCR tùy chọn; sau 03/TNDN có 351 test OK. Ruff và
mypy (43 file) qua trên Linux/Python 3.11. Ma trận Python 3.10/3.12 được kiểm tra
trên pipeline GitLab của MR.

Môi trường `.venv` đang trỏ Python đã bị gỡ. Đã tạo riêng `.venv-review` dùng
Python 3.11, cài thư viện test/lint, không thay môi trường cũ. Các test có nhiều
atomic replace dùng cleanup retry riêng cho WinError 145 tạm thời; lỗi log/file
handle còn mở không bị bỏ qua.

## Test thật bằng cấu hình `.env`

Chạy ngày 27/09/2026, khoảng `01/09/2018`–`25/10/2018`, hai đoạn tra cứu,
solver `ddddocr`, không proxy, DVC bị tắt. Harness riêng có chặn request tới
DVC, đếm request và kiểm tra kết quả; không đưa harness/log/ZIP thật vào Git.

| Kiểm tra | Lần đầu | Chạy lại cùng cấu hình |
|---|---|---|
| Mã thoát | 0 | 0 |
| Hồ sơ khả dụng | 6/6 | 6/6, dùng lại ZIP có sẵn |
| HTTP tới legacy | 20 | 17 |
| HTTP tới DVC | 0 | 0 |
| Request tải `downTkhai` | 6 | 0 |
| ZIP/XML | 6 ZIP hợp lệ, 6 XML well-formed | 6 ZIP hợp lệ, 6 XML well-formed |
| Metadata | Giữ dữ liệu cũ; 12 dòng JSON/CSV sau gộp | Vẫn 12 dòng, không thêm trùng |

Index nhóm `schema_version=1` tham chiếu đúng 6 hồ sơ có file. Với 6 hồ sơ
vừa kiểm tra: một `04/GTGT` được nhận GTGT/DECLARATION; bốn bảng `02TH` đăng ký
người phụ thuộc và một báo cáo `BC26/AC` còn UNKNOWN. Đây là giới hạn của rule
metadata hiện tại, không tự gán TNCN từ suy đoán. Cần fixture ẩn danh và rule
có bằng chứng ở stage 02–03.

Report cục bộ (đã bỏ thông tin đăng nhập, nhưng cả thư mục log vẫn là riêng tư):

- `logs/live-test-20260927-091236/report.json`
- `logs/live-test-20260927-091324/report.json`

Các đường dẫn này không tồn tại sau clone mới, trừ khi chuyển riêng từ máy cũ.
Không có log/fixture thật mới nào được đưa vào commit.

XML well-formed không có nghĩa là đã kiểm đúng schema hay đọc đúng chỉ tiêu.
Test này không xác nhận mọi mẫu, mọi kỳ, mọi tài khoản, độ chính xác OCR tổng
quát hoặc hoạt động của DVC. Test offline vẫn là lớp bảo vệ chính; test thật
sau này chỉ chạy trên khoảng nhỏ được cho phép, không bật DVC mặc định chỉ
vì adapter có test qua. Xem [HANDOFF](HANDOFF.md) để tái lập môi trường và làm tiếp.
