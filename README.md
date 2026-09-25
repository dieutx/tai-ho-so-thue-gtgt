# Tải hồ sơ thuế GTGT từ Dịch vụ công Thuế

Công cụ Python tự đăng nhập Cổng Dịch vụ công của Cục Thuế, nhận dạng CAPTCHA,
tra cứu hồ sơ theo khoảng ngày và tải về dưới dạng ZIP kèm danh sách chi tiết.

Chạy được trên **Windows và Linux**, Python **3.10+**.

## Chức năng

- Tự chia khoảng tra cứu dài thành các đoạn **tối đa 31 ngày** — giới hạn của cổng.
- Tự chọn nguồn dữ liệu theo ngày nộp hồ sơ:
  - trước `01/07/2025` → luồng **ETAX** (Thuế điện tử)
  - từ `01/07/2025` → luồng **DVC** (Dịch vụ công hiện hành)
- Xử lý đầy đủ phân trang và tải ngay trên từng trang để giữ trạng thái phiên.
- Nhận dạng CAPTCHA đăng nhập và tra cứu; **có thể thay bằng bộ nhận dạng khác**
  khi cổng đổi kiểu CAPTCHA (xem [Cấu hình](#cấu-hình)).
- Đặt tên ZIP gợi nhớ: mã hồ sơ, kỳ tính thuế, **loại tờ khai**, tên tờ khai.
- Xuất `danh_sach_ho_so.csv` và `danh_sach_ho_so.json` cho biết loại từng tờ khai.
- Bỏ qua ZIP đã tải hợp lệ, nên chạy tiếp được khi bị gián đoạn.
- Tự thử lại khi cổng trả về `429 Too Many Requests`.
- Chế độ `--dry-run` chỉ tra cứu, không tải file.

## Cài đặt

### Windows (PowerShell)

```powershell
git clone https://github.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Linux / macOS

```bash
git clone https://github.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Lần chạy đầu tiên `easyocr` sẽ tải mô hình nhận dạng (vài chục MB).

## Cấu hình

Sao chép `.env.example` thành `.env` rồi điền thông tin thật:

```dotenv
GDT_USERNAME=ma_so_thue-QL
GDT_PASSWORD=mat_khau_dich_vu_cong
GDT_FROM_DATE=01/01/2026
GDT_TO_DATE=31/01/2026
GDT_DOWNLOAD_DIR=download
```

File `.env` đã nằm trong `.gitignore`. Biến môi trường thật luôn **ghi đè** giá trị
trong `.env`, nên có thể chạy nhanh mà không cần sửa file:

```bash
GDT_FROM_DATE=01/01/2025 GDT_TO_DATE=31/01/2025 python -m gdt_tax
```

Bảng biến đầy đủ ở [`.env.example`](.env.example). Các biến hay dùng:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `GDT_USERNAME` | — | Tên đăng nhập (bắt buộc) |
| `GDT_PASSWORD` | — | Mật khẩu (bắt buộc) |
| `GDT_FROM_DATE` / `GDT_TO_DATE` | `01/09/2026` / `25/09/2026` | Khoảng ngày `dd/mm/yyyy` |
| `GDT_DOWNLOAD_DIR` | `download` | Thư mục lưu ZIP và metadata |
| `GDT_CASE_ID` | trống | Chỉ tải một mã hồ sơ |
| `GDT_CAPTCHA_SOLVER` | `easyocr` | `easyocr`, `manual`, `remote` hoặc solver riêng |
| `GDT_ETAX_CUTOFF` | `01/07/2025` | Mốc chuyển từ ETAX sang DVC |
| `GDT_MAX_DAYS_PER_SEARCH` | `31` | Số ngày tối đa mỗi đoạn tra cứu |
| `GDT_DRY_RUN` | `false` | Chỉ tra cứu, không tải |

## Chạy

```bash
# Tải hồ sơ tháng 1/2025 (luồng ETAX) vào thư mục riêng
python -m gdt_tax --from-date 01/01/2025 --to-date 31/01/2025 --output-dir download/2025-01

# Tải hồ sơ tháng 1/2026 (luồng DVC)
python -m gdt_tax --from-date 01/01/2026 --to-date 31/01/2026 --output-dir download/2026-01

# Chỉ một hồ sơ
python -m gdt_tax --case-id 11320250292469209

# Chỉ tra cứu, không tải
python -m gdt_tax --dry-run

# Xem các bộ nhận dạng CAPTCHA có sẵn
python -m gdt_tax --list-solvers
```

Sau khi `pip install -e .` có thể dùng lệnh ngắn `gdt-tax ...`.
Script `taitokhaiGTGT_fix_v12_full.py` vẫn chạy được như cũ và chỉ còn là lớp
gọi mỏng vào gói `gdt_tax`.

Mã thoát: `0` thành công, `1` chạy xong nhưng thiếu hồ sơ, `2` lỗi cấu hình.

## Kết quả

```text
download/2025-01/
├── 11320250292469209__12-2024__Chinh-thuc__TO-KHAI-THUE-GIA-TRI-GIA-TANG-TT80-2021.zip
├── 11320250292528963__12-2024__Chinh-thuc__To-khai-khau-tru-thue-thu-nhap-ca-nhan-TT80.zip
├── danh_sach_ho_so.csv
└── danh_sach_ho_so.json
```

Mỗi dòng metadata có: mã hồ sơ, nguồn, tên TTHC, tờ khai, kỳ tính thuế,
**loại tờ khai**, lần nộp, lần bổ sung, ngày nộp, nơi nộp, trạng thái, tên file ZIP.

## Kiểm thử

Toàn bộ test chạy **offline** (dùng HTTP giả), không cần tài khoản hay Internet:

```bash
python -m unittest discover -s tests -t . -v
```

Muốn lint:

```bash
python -m pip install -r requirements-dev.txt
ruff check .
```

## Cấu trúc dự án

```text
gdt_tax/
├── cli.py             # dòng lệnh, mã thoát
├── config.py          # cấu hình từ .env và biến môi trường
├── dates.py           # quy tắc ngày tháng, chia đoạn 31 ngày
├── pipeline.py        # 5 giai đoạn của một lần chạy
├── auth.py            # đăng nhập, mở trang hồ sơ
├── http.py            # HTTP + tự thử lại khi bị 429
├── csrf.py            # đọc CSRF token
├── parsing.py         # đọc bảng kết quả ETAX/DVC
├── naming.py          # đặt tên file ZIP
├── storage.py         # lưu ZIP, xuất CSV/JSON
├── captcha/           # bộ nhận dạng CAPTCHA có thể thay thế
└── portals/           # cách tra cứu/tải riêng cho DVC và ETAX
```

Chi tiết luồng chạy và cách mở rộng: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Cách đóng góp: [CONTRIBUTING.md](CONTRIBUTING.md).

## Lưu ý

- Chỉ dùng với tài khoản và hồ sơ mà bạn có quyền truy cập.
- Giao diện và endpoint của cổng Dịch vụ công có thể thay đổi bất cứ lúc nào;
  khi đó cập nhật `gdt_tax/constants.py`, `gdt_tax/parsing.py` hoặc portal tương ứng.
- Không commit tài khoản, mật khẩu, cookie hay CSRF token vào repository.
