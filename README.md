# Tải hồ sơ thuế điện tử

[![CI](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/badges/main/pipeline.svg)](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/pipelines)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Công cụ Python để tra cứu, tải và tổng hợp hồ sơ thuế điện tử theo khoảng ngày.
Chương trình lưu hồ sơ gốc, metadata và báo cáo Excel; lần chạy sau tự dùng lại
ZIP hợp lệ đã có.

> Trạng thái nguồn dữ liệu: trước ngày cutoff dùng Thuế điện tử (legacy). Từ
> cutoff trở đi thuộc Dịch vụ công (DVC), nhưng DVC đang mặc định tắt cho đến khi
> dữ liệu và endpoint được xác minh ổn định.

Hỗ trợ Windows, Linux và macOS với Python 3.10 trở lên.

## Chức năng chính

- Tự chia khoảng tra cứu thành các đoạn tối đa 31 ngày.
- Tự đăng nhập và nhận dạng CAPTCHA bằng `ddddocr`.
- Duyệt đủ phân trang, tải hồ sơ và tiếp tục được sau khi gián đoạn.
- Trước cutoff dùng trực tiếp `thuedientu.gdt.gov.vn`.
- DVC có thể bật lại bằng cấu hình, nhưng mặc định không được gọi.
- Xuất danh sách tờ khai Excel 11 cột từ kết quả tra cứu.
- Tra cứu giấy nộp tiền và tải XML về, kèm Excel tổng hợp (lệnh `gdt-gnt`).
- Tra cứu thông báo của cơ quan thuế và tải PDF về, kèm Excel tổng hợp (lệnh `gdt-tb`).
- Kiểm kê, phân loại và đọc chỉ tiêu XML hoàn toàn offline.
- Xuất workbook phân tích nhiều sheet, giữ mọi lần nộp và thông tin nguồn.

## Chính sách nguồn theo ngày

| Khoảng ngày | Nguồn | Mặc định |
|---|---|---|
| Trước `01/07/2025` | Thuế điện tử legacy | Bật |
| Từ `01/07/2025` | Cổng Dịch vụ công | Tắt |

Nếu khoảng tra cứu đi qua cutoff, phần legacy vẫn chạy. Phần DVC bị bỏ qua được
báo rõ và chương trình trả mã thoát `1` để tránh hiểu nhầm kết quả là đầy đủ.

Có thể đổi cutoff bằng `GDT_ETAX_CUTOFF`. Chỉ bật DVC khi chủ động kiểm thử:

```bash
python -m gdt_tax --enable-dvc
```

## Cài đặt nhanh

Clone từ GitLab — đây là repository chính:

```bash
git clone https://gitlab.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux hoặc macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Repo private sẽ yêu cầu credential GitLab. Không đưa token vào URL, `.env`,
issue, log hoặc commit.

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
GDT_FROM_DATE=01/06/2025
GDT_TO_DATE=30/06/2025
GDT_DOWNLOAD_DIR=download

GDT_LEGACY_ETAX=true
GDT_DVC_ENABLED=false
GDT_ETAX_CUTOFF=01/07/2025
```

Tham số dòng lệnh ưu tiên hơn biến môi trường; biến môi trường ưu tiên hơn
`.env`. File `.env` đã nằm trong `.gitignore`.

Các cấu hình CAPTCHA, retry, log, proxy và header mẫu có trong
[.env.example](.env.example).

## Sử dụng

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

Chỉ tải một hồ sơ:

```bash
python -m gdt_tax --case-id <ma-ho-so>
```

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

Thư mục `download/` chứa ZIP hồ sơ và các báo cáo sau:

| File | Nội dung |
|---|---|
| `danh_sach_to_khai.xlsx` | Danh sách tờ khai nghiệp vụ |
| `danh_sach_ho_so.csv` / `.json` | Metadata đầy đủ để tích hợp |
| `phan_loai_ho_so.json` | Nhóm hồ sơ theo metadata |
| `manifest_artifact.json` | Inventory file/member, hash và cấu trúc XML |
| `parsed_declarations.json` | Metadata và chỉ tiêu đã parse |
| `phan_loai_artifact.json` | Phân loại từng artifact theo nội dung |
| `Tax_Return_Summary.xlsx` | Workbook phân tích nhiều sheet |

`danh_sach_to_khai.xlsx` có đúng 11 cột:

| STT | Mã hồ sơ | Tên tờ khai | Kỳ tính thuế | Loại tờ khai | Lần nộp bổ sung | Lần nộp | Cơ quan thuế tiếp nhận | Ngày nộp | Trạng thái | Hồ sơ đính kèm |
|---:|---|---|---|---|---:|---:|---|---|---|---|

Dữ liệu cũ được gộp theo nguồn và mã hồ sơ. Ô có khả năng bị Excel hiểu là
công thức được escape; `null`, `0` và số âm vẫn được phân biệt.

## Phân tích XML offline

Các lệnh này không đăng nhập và không gọi cổng thuế:

```bash
python -m gdt_tax.inventory download --output download
python -m gdt_tax.parser.cli download --output download
python -m gdt_tax.classify download --output download
python -m gdt_tax.export download --output download
```

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

Kết quả kiểm chứng trên bộ dữ liệu cục bộ hiện tại: 1.265 XML, 0 lỗi parse,
479 tờ khai `MAPPED`; riêng 03/TNDN là 20/20 hồ sơ, không warning. Dữ liệu thật
không được đưa vào Git.

## Nguyên tắc dữ liệu

- Không commit `.env`, ZIP/XML/PDF thật, log hoặc HTTP dump.
- Không tự tính lại thuế, thuế suất, chuyển lỗ hay ưu đãi.
- Không cộng dồn nhiều lần nộp cùng kỳ và không tự chọn bản bổ sung “mới nhất”.
- Giữ `source_zip`, `source_inner_file`, SHA-256 và XPath để kiểm toán.
- HTTP dump có thể chứa dữ liệu nhạy cảm dù log thông thường đã che nhiều trường.

## Kiểm thử

Cài dependency phát triển:

```bash
python -m pip install -r requirements-dev.txt
```

Chạy cùng các kiểm tra CI:

```bash
python -m unittest discover -s tests -t . -v
python -m ruff check .
python -m mypy gdt_tax
```

Hiện có 352 test; 6 test backend OCR tùy chọn được skip nếu chưa cài EasyOCR
hoặc PaddleOCR. GitLab CI chạy test trên Python 3.10 và 3.12, cùng lint/mypy.

## Khắc phục nhanh

- CAPTCHA sai nhiều lần: dùng `--solver manual`.
- Chạy trên máy chủ ngoài Việt Nam: cấu hình proxy Việt Nam bằng
  `GDT_PROXY_URL` hoặc `--proxy`.
- Khoảng sau cutoff không có dữ liệu: đây là hành vi dự kiến khi DVC đang tắt.
- Cổng đổi HTML/endpoint: chạy với `--log-file`; chỉ dùng `--dump-http` trong
  môi trường riêng tư.
- Muốn chạy lại từ đầu: dùng thư mục output mới. Không xóa dữ liệu cũ nếu chưa
  sao lưu.

## Tài liệu kỹ thuật

- [Kiến trúc](docs/ARCHITECTURE.md)
- [Kết quả rà soát và giới hạn](docs/development/REVIEW.md)
- [Roadmap phát triển](docs/development/README.md)
- [Bàn giao môi trường](docs/development/HANDOFF.md)
- [Quy ước form mapping](gdt_tax/form_mappings/README.md)
- [Hướng dẫn thêm mẫu biểu (form mapping) mới](docs/HUONGDAN_THEM_MAPPING.md)
- [Hướng dẫn đóng góp](CONTRIBUTING.md)

## Giấy phép

MIT — xem [LICENSE](LICENSE).

Công cụ không phải sản phẩm chính thức của cơ quan thuế. Người dùng chịu trách
nhiệm về tài khoản, phạm vi truy cập, dữ liệu tải về và việc tuân thủ quy định
áp dụng.
