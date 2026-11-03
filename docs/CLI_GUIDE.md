# Chạy Tải Hồ Sơ Thuế bằng Python

Hướng dẫn cài đặt, cấu hình `.env` và các lệnh Python/CLI như trước đây.
Nếu cần chạy giao diện desktop từ Python, xem [hướng dẫn phát triển](../BUILD_WINDOWS.md#build).

[![CI](https://github.com/dieutx/tai-ho-so-thue-gtgt/actions/workflows/ci.yml/badge.svg)](https://github.com/dieutx/tai-ho-so-thue-gtgt/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](../pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](../LICENSE)

Công cụ Python để tra cứu, tải và tổng hợp hồ sơ thuế điện tử theo khoảng ngày.
Chương trình lưu hồ sơ gốc, metadata và báo cáo Excel; lần chạy sau tự dùng lại
ZIP hợp lệ đã có.

Khoảng ngày được tự chia thành các đoạn tối đa 31 ngày. Chương trình duyệt
phân trang, hỗ trợ CAPTCHA tự động hoặc nhập tay và giữ mọi lần nộp khi phân
tích XML offline.

> Trạng thái nguồn dữ liệu: trước ngày cutoff dùng Thuế điện tử (legacy). Từ
> cutoff trở đi thuộc Dịch vụ công (DVC). Desktop 1.1 bật DVC mặc định theo yêu
> cầu sử dụng; CLI vẫn mặc định tắt và bật bằng `--enable-dvc`. Đã kiểm tra tải
> thật cả DVC/GNT/thông báo ngày 19/10/2026; xem phạm vi trong báo cáo nghiệm thu.

Hỗ trợ Windows, Linux và macOS với Python 3.10 trở lên.

| Nhu cầu | Lệnh | Kết quả chính |
|---|---|---|
| Tải hồ sơ/tờ khai | `gdt-tax` | ZIP gốc và danh sách tờ khai Excel |
| Tải giấy nộp tiền | `gdt-gnt` | XML gốc và danh sách GNT Excel |
| Tải thông báo của cơ quan thuế | `gdt-tb` | PDF gốc và danh sách thông báo Excel |
| Kiểm kê, đọc và phân loại XML offline | `gdt-inventory`, `gdt-parse`, `gdt-classify` | Manifest, chỉ tiêu và phân loại artifact |
| Xuất workbook phân tích | `gdt-export` | `Tax_Return_Summary.xlsx` |

## Mục lục

Ứng dụng Windows PySide6: chạy `python -m desktop.main`, hoặc dùng một file
`dist/TaiHoSoThue-Windows.exe` sau khi build. Một tài khoản nhập một lần ở
header; ba nghiệp vụ online dùng chung phiên ETAX, còn Offline không cần tài
khoản/mạng. Bản Full 1.1 vẫn có CAPTCHA tự động, mục phiên bản/cập nhật và
trạng thái tệp đã có hợp lệ. Xem
[hướng dẫn desktop/build](../BUILD_WINDOWS.md),
[bản đồ chức năng UI](../docs/UI_FUNCTION_MAPPING.md) và
[báo cáo dung lượng](../docs/BUILD_SIZE_REPORT.md).

- [Cài đặt nhanh](#cài-đặt-nhanh)
- [Cấu hình](#cấu-hình-bằng-env)
- [Chính sách nguồn theo ngày](#chính-sách-nguồn-theo-ngày)
- [Tờ khai](#sử-dụng), [giấy nộp tiền](#tra-cứu-giấy-nộp-tiền-gnt), [thông báo](#tra-cứu-thông-báo-của-cơ-quan-thuế)
- [Báo cáo đầu ra](#báo-cáo-đầu-ra)
- [Phân tích XML offline](#phân-tích-xml-offline)
- [Kiểm thử](#kiểm-thử)
- [Chẩn đoán và khắc phục](#chẩn-đoán-và-khắc-phục)
- [Tài liệu kỹ thuật](#tài-liệu-kỹ-thuật)

## Cài đặt nhanh

Clone từ GitHub — đây là repository chính:

```bash
git clone https://github.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[ocr-ddddocr]"
```

Linux hoặc macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[ocr-ddddocr]"
```

Cách cài trên tạo đầy đủ lệnh `gdt-*` và cài backend CAPTCHA mặc định `ddddocr`.
Nếu chỉ cần nhập CAPTCHA bằng tay hoặc phân tích offline, cài
`python -m pip install -e .` rồi dùng `--solver manual` khi tra cứu.

Nếu PowerShell không cho kích hoạt venv, dùng trực tiếp Python của môi trường:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ocr-ddddocr]"
.\.venv\Scripts\python.exe -m gdt_tax --help
```

Khi chưa kích hoạt venv, thay `python` trong các ví dụ bằng
`.\.venv\Scripts\python.exe`; lệnh `gdt-*` nằm trong `.\.venv\Scripts\`.
Cài bằng `requirements.txt` vẫn chạy được qua `python -m` từ repo nhưng không
tạo các lệnh `gdt-*`.

Repo public, không cần credential. Không đưa token vào URL, `.env`, issue, log
hoặc commit.

## Cấu hình bằng `.env`

Tạo file cấu hình cục bộ:

```bash
cp .env.example .env
```

Trên PowerShell:

```powershell
Copy-Item .env.example .env
```

Cấu hình tối thiểu:

```dotenv
GDT_USERNAME=ma_so_thue-QL
GDT_PASSWORD=mat_khau_thue_dien_tu
GDT_ACCOUNT_TYPE=DN
GDT_FROM_DATE=01/06/2025
GDT_TO_DATE=30/06/2025
GDT_DOWNLOAD_DIR=download

GDT_LEGACY_ETAX=true
GDT_DVC_ENABLED=false
GDT_ETAX_CUTOFF=01/07/2025
```

Với cá nhân, đặt `GDT_ACCOUNT_TYPE=CN` hoặc dùng `--account-type CN`.
Tờ khai từ cutoff dùng DVC khi bật `--enable-dvc`; trước cutoff dùng cổng cá nhân
`canhan.gdt.gov.vn`. Thông báo cá nhân dùng cổng cũ; GNT cá nhân chưa hỗ trợ.
Xem [luồng cá nhân và kiểm chứng](PERSONAL_ACCOUNTS.md).

Tham số dòng lệnh ưu tiên hơn biến môi trường; biến môi trường ưu tiên hơn
`.env`. File `.env` đã nằm trong `.gitignore`.

Nếu bỏ ngày, mặc định là tháng ngay trước cutoff (tháng 06/2025 với cutoff
trên). `GDT_MAX_DAYS_PER_SEARCH` nhận giá trị từ 1 đến 31; khoảng tổng thể có
thể dài hơn và được tự chia nhỏ. Nên dùng thư mục đầu ra riêng cho mỗi tài khoản.

Các cấu hình CAPTCHA, retry, log, proxy và header mẫu có trong
[.env.example](../.env.example).

## Chính sách nguồn theo ngày

Chính sách này áp dụng cho **tờ khai (`gdt-tax`)**. GNT và thông báo dùng Thuế
điện tử legacy cho toàn bộ khoảng ngày, không chuyển nguồn theo cutoff.

| Khoảng ngày | Nguồn | Mặc định |
|---|---|---|
| Trước `01/07/2025` | Thuế điện tử legacy | Bật |
| Từ `01/07/2025` | Cổng Dịch vụ công | Tắt |

Nếu khoảng tra cứu đi qua cutoff, phần legacy vẫn chạy. Phần DVC bị bỏ qua được
báo rõ và chương trình trả mã thoát `1`, kể cả dry-run, để tránh hiểu nhầm kết
quả là đầy đủ. Có thể đổi cutoff bằng `GDT_ETAX_CUTOFF`.

Chỉ bật DVC khi chủ động kiểm thử:

```bash
python -m gdt_tax --from-date 01/07/2025 --to-date 31/07/2025 --enable-dvc
```

## Sử dụng

Tài khoản cá nhân dùng cổng riêng `canhan.gdt.gov.vn`. Chọn `--account-type CN`
cho cả tờ khai và thông báo; cờ này bỏ qua cutoff/DVC của doanh nghiệp và tự
chia khoảng ngày thành các đoạn 31 ngày:

```bash
python -m gdt_tax --account-type CN --from-date 01/01/2022 --to-date 03/11/2026
python -m gdt_tax.tb --account-type CN --from-date 01/01/2022 --to-date 03/11/2026
```

Không truyền cờ này thì mặc định là tài khoản doanh nghiệp (`DN`). CAPTCHA cổng
cá nhân dài 4 hoặc 5 ký tự; bộ đọc `ddddocr` tự nhận cả hai độ dài khi dùng
`--account-type CN`.

Chạy theo ngày trong `.env`:

```bash
python -m gdt_tax
```

Ghi đè khoảng ngày:

```bash
python -m gdt_tax --from-date 01/01/2025 --to-date 31/01/2025
```

Chỉ tra cứu, không tải:

```bash
python -m gdt_tax --dry-run
```

`--dry-run` vẫn đăng nhập, tra cứu và cập nhật danh sách metadata; tham chiếu
file đã tải ở lần trước được giữ lại.

Chỉ tải một hồ sơ:

```bash
python -m gdt_tax --case-id MA_HO_SO
```

`--case-id` tìm hồ sơ trong khoảng ngày đang cấu hình.

Với hồ sơ DVC và legacy, mỗi hồ sơ tải xong còn được lấy các **thông báo đính
kèm** (tiếp nhận, chấp nhận, không chấp nhận) và lưu vào
`<nơi lưu>/thong-bao-dinh-kem/<mã hồ sơ>/`. Tệp đã có được bỏ qua; lỗi tải
thông báo không làm hỏng ZIP đã tải; báo cáo ghi riêng trạng thái thông báo
chưa đầy đủ, không coi trang lạ hoặc chỉ đọc được một phần là rỗng thành công.

Chương trình không đặt mốc chặn ngày `01/01/2015`; khoảng ngày cũ vẫn gửi đến
legacy theo từng đoạn tối đa 31 ngày. XML cũ có DOCTYPE không ENTITY và ZIP
trả trực tiếp dùng chung bộ xác minh khi tải/lưu/resume/đọc offline.
Kết quả rỗng không đủ chứng minh cổng đã xóa hồ sơ; cần đối chiếu tài khoản,
quyền truy cập, khoảng ngày và kết quả tra cứu trên cổng. Lượt sửa này chỉ
kiểm thử offline, chưa xác nhận lấy được hồ sơ thật trước 2015.

Một số lệnh hữu ích:

```bash
python -m gdt_tax --list-solvers
python -m gdt_tax --solver manual
python -m gdt_tax --log-file logs/gdt.log -v
python -m gdt_tax --proxy http://user:password@host:port
```

Xem toàn bộ tham số:

```bash
python -m gdt_tax --help
```

| Mã thoát của lệnh tải | Ý nghĩa |
|---:|---|
| `0` | Thành công; với dry-run là tra cứu thành công |
| `1` | Chưa đầy đủ, có phần bị bỏ qua hoặc lỗi trong quá trình chạy |
| `2` | Lỗi cấu hình hoặc khởi tạo CAPTCHA |

## Tra cứu giấy nộp tiền (GNT)

Giấy nộp tiền nằm trên trang Thuế điện tử cũ, dùng chung phiên đăng nhập với tờ
khai nhưng là một lệnh riêng (`corpQueryTaxProc`). Lệnh này chỉ **tải XML** của GNT
về và xuất Excel tổng hợp; **không** parse chỉ tiêu bên trong XML.

```bash
python -m gdt_tax.gnt --from-date 01/09/2026 --to-date 30/09/2026
gdt-gnt --from-date 01/09/2026 --to-date 30/09/2026 --output-dir download/gnt-2026-09
python -m gdt_tax.gnt --dry-run          # chỉ tra cứu, không tải
```

Khoảng dài hơn 31 ngày tự chia nhỏ theo ngày lập GNT. Đầu ra trong `--output-dir`:

| File | Nội dung |
|---|---|
| `<số GNT>__<ctuId>.xml` | XML gốc của từng giấy nộp tiền |
| `danh_sach_giay_nop_tien.xlsx` | Bảng tổng hợp 20 cột: số GNT, số tiền, loại tiền, trạng thái, số chứng từ, ngày lập/gửi/nộp, hình thức nộp, ngân hàng, tài khoản, file XML… |
| `danh_sach_giay_nop_tien.csv` / `.json` | Metadata đầy đủ để tích hợp |

File XML đã tải hợp lệ được bỏ qua ở lần chạy sau nên chạy tiếp được khi gián
đoạn. Các cờ và biến môi trường (solver, proxy, log, header, `GDT_FROM_DATE`…)
dùng chung với `gdt-tax`; xem `python -m gdt_tax.gnt --help`.

## Tra cứu thông báo của cơ quan thuế

Thông báo của cơ quan thuế (thông báo tiền thuế nợ, quyết định cưỡng chế…) nằm
cùng trang Thuế điện tử cũ, dùng chung phiên đăng nhập nhưng là một lệnh riêng
(`tracuuTBThueKhacProc`). Lệnh này tải **PDF** của từng thông báo và xuất Excel
tổng hợp; không parse nội dung PDF.

```bash
python -m gdt_tax.tb --from-date 01/08/2026 --to-date 30/09/2026
gdt-tb --from-date 01/08/2026 --to-date 30/09/2026 --output-dir download/tb-2026-08-09
python -m gdt_tax.tb --dry-run          # chỉ tra cứu, không tải
```

Khoảng ngày lọc theo **ngày gửi/nộp thông báo**; khoảng dài hơn 31 ngày tự chia
nhỏ. Đầu ra trong `--output-dir`:

| File | Nội dung |
|---|---|
| `<số thông báo>__<messageId>.pdf` | PDF gốc của từng thông báo |
| `danh_sach_thong_bao.xlsx` | Bảng tổng hợp: mã/tên/số thông báo, ngày gửi, cơ quan gửi, trạng thái (đã xem/chưa xem), có văn bản giải trình/phản hồi, file PDF |
| `danh_sach_thong_bao.csv` / `.json` | Metadata đầy đủ để tích hợp |

File PDF đã tải hợp lệ được bỏ qua ở lần chạy sau. Các cờ và biến môi trường
dùng chung với `gdt-tax`; xem `python -m gdt_tax.tb --help`.

## Báo cáo đầu ra

### Báo cáo tạo khi tra cứu/tải

Thư mục `GDT_DOWNLOAD_DIR` (mặc định `download/`) hoặc `--output-dir` chứa ZIP
hồ sơ và các báo cáo sau. Đầu ra GNT/thông báo được mô tả ở từng mục bên trên.

| File | Nội dung |
|---|---|
| `danh_sach_to_khai.xlsx` | Danh sách tờ khai nghiệp vụ |
| `danh_sach_ho_so.csv` / `.json` | Metadata đầy đủ để tích hợp |
| `phan_loai_ho_so.json` | Nhóm hồ sơ theo metadata |

`danh_sach_to_khai.xlsx` có đúng 11 cột:

STT, mã hồ sơ, tên tờ khai, kỳ tính thuế, loại tờ khai, lần nộp bổ sung, lần nộp,
cơ quan thuế tiếp nhận, ngày nộp, trạng thái và hồ sơ đính kèm.

Dữ liệu cũ được gộp theo nguồn và mã hồ sơ. Ô có khả năng bị Excel hiểu là
công thức được escape; `null`, `0` và số âm vẫn được phân biệt.

ZIP được kiểm tra CRC và giới hạn trước khi giải nén: tối đa 256 MiB dữ liệu
ZIP, 200 member, 64 MiB/member, tổng 256 MiB sau giải nén và tỉ lệ nén 200:1.
ZIP mã hóa hoặc vượt giới hạn bị từ chối và không được tính là tải thành công.

### Báo cáo tạo bằng lệnh offline

Các file này chỉ được tạo sau khi chạy các lệnh ở mục tiếp theo:

| File | Nội dung |
|---|---|
| `manifest_artifact.json` | Inventory file/member, hash và cấu trúc XML |
| `bao_cao_discovery.json` / `.md` | Thống kê cấu trúc, mẫu và phiên bản |
| `parsed_declarations.json` | Metadata và chỉ tiêu đã parse |
| `phan_loai_artifact.json` | Phân loại từng artifact theo nội dung |
| `Tax_Return_Summary.xlsx` | Workbook phân tích nhiều sheet |

## Phân tích XML offline

Chạy lần lượt sau khi có dữ liệu tải về. Các lệnh này không đăng nhập và không
gọi cổng thuế:

```bash
python -m gdt_tax.inventory download --output download
python -m gdt_tax.parser.cli download --output download
python -m gdt_tax.classify download --output download
python -m gdt_tax.export download --output download
```

Inventory tạo manifest cho parser và classifier; exporter ghép kết quả thành
workbook. Báo cáo do chương trình tạo ra được bỏ qua khi kiểm kê lại.
Nếu dùng thư mục tải khác, thay `download` trong các lệnh trên.

Workbook `Tax_Return_Summary.xlsx` gồm index tờ khai, các sheet GTGT/TNCN/TNDN,
chỉ tiêu dạng dài, mẫu chưa mapping, lỗi parse, phiên bản mapping và audit log.
Mỗi dòng giữ đường dẫn ZIP/member, SHA-256 và XPath để truy vết.

### Mẫu đã có mapping

| Nhóm | Mẫu | Mã mẫu XML | Phạm vi |
|---|---|---:|---|
| GTGT | 01/GTGT | 842 | Chỉ tiêu tổng hợp |
| TNCN | 05/KK-TNCN TT80 | 864 | Chỉ tiêu tổng hợp |
| TNCN | 05/KK-TNCN TT92 | 394 | Chỉ tiêu tổng hợp |
| TNDN | 03/TNDN | 892 | XML 2.5.1 và 2.9.4 |

Mapping 03/TNDN chỉ đọc tờ khai chính, không gán báo cáo tài chính hoặc phụ lục
thành tờ khai. Version chưa được xác minh giữ trạng thái `NEED_MAPPING`; parser
không suy đoán ý nghĩa chỉ tiêu.

Số liệu kiểm chứng theo từng lần rà soát nằm trong
[REVIEW.md](../docs/development/REVIEW.md). Dữ liệu thật không được đưa vào Git.

## Nguyên tắc dữ liệu

- Không commit `.env`, ZIP/XML/PDF thật, log hoặc HTTP dump.
- Không tự tính lại thuế, thuế suất, chuyển lỗ hay ưu đãi.
- Không cộng dồn nhiều lần nộp cùng kỳ và không tự chọn bản bổ sung “mới nhất”.
- Giữ `source_zip`, `source_inner_file`, SHA-256 và XPath để kiểm toán.
- `--dump-http` ghi metadata/hash đã làm sạch, không ghi payload gốc.
- `--dump-http-private` (hoặc `GDT_HTTP_DUMP_PRIVATE=true`) bật raw response
  trong thư mục `PRIVATE`, tối đa 100 request trong 15 phút, 2 MB/body.
  Dữ liệu này vẫn nhạy cảm: không đưa vào gói hỗ trợ, xóa sau khi chẩn đoán.

## Kiểm thử

Cài công cụ phát triển trong venv; test offline không cần tài khoản hoặc OCR:

```bash
python -m pip install -e ".[dev]"
```

Chạy cùng các kiểm tra CI:

```bash
python -m unittest discover -s tests -t . -v
python -m ruff check .
python -m mypy gdt_tax
```

Các test backend OCR tùy chọn có thể được skip nếu thiếu thư viện tương ứng.
GitHub Actions chạy test trên Python 3.10 và 3.12, cùng lint/mypy. Test offline không
xác nhận cổng thuế hiện đang hoạt động hoặc mọi mẫu XML đều được hỗ trợ.

## Chẩn đoán và khắc phục

- Không tìm thấy `gdt-*`: kích hoạt venv và cài package bằng `pip install -e .`,
  hoặc dùng `python -m`.
- CAPTCHA sai nhiều lần: dùng `--solver manual`.
- Chạy trên máy chủ ngoài Việt Nam: cấu hình proxy Việt Nam bằng
  `GDT_PROXY_URL` hoặc `--proxy`.
- Khoảng sau cutoff không có dữ liệu: đây là hành vi dự kiến khi DVC đang tắt.
- Cổng đổi HTML/endpoint: dùng `--log-file` hoặc metadata từ `--dump-http`.
  Chỉ bật `--dump-http-private` khi cần điều tra riêng tư.
- Excel đang mở gây lỗi ghi báo cáo: đóng workbook rồi chạy lại; file gốc hợp
  lệ được dùng lại.
- Muốn chạy lại từ đầu: dùng thư mục output mới. Không xóa dữ liệu cũ nếu chưa
  sao lưu.

## Tài liệu kỹ thuật

- [Kiến trúc](../docs/ARCHITECTURE.md)
- [Thiết kế desktop compact](../docs/DESKTOP_UI_DESIGN.md)
- [Kết quả kiểm thử desktop](../docs/DESKTOP_ACCEPTANCE.md)
- [Báo cáo dung lượng Full EXE](../docs/BUILD_SIZE_REPORT.md)
- [Kết quả rà soát và giới hạn](../docs/development/REVIEW.md)
- [Roadmap phát triển](../docs/development/README.md)
- [Bàn giao môi trường](../docs/development/HANDOFF.md)
- [Quy ước form mapping](../gdt_tax/form_mappings/README.md)
- [Hướng dẫn thêm mẫu biểu (form mapping) mới](../docs/HUONGDAN_THEM_MAPPING.md)
- [Hướng dẫn đóng góp](../CONTRIBUTING.md)

## Giấy phép

MIT — xem [LICENSE](../LICENSE).

Công cụ không phải sản phẩm chính thức của cơ quan thuế. Người dùng chịu trách
nhiệm về tài khoản, phạm vi truy cập, dữ liệu tải về và việc tuân thủ quy định
áp dụng.
