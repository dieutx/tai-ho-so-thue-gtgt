# Tải hồ sơ thuế GTGT từ Cổng Dịch vụ công

[![CI](https://github.com/dieutx/tai-ho-so-thue-gtgt/actions/workflows/ci.yml/badge.svg)](https://github.com/dieutx/tai-ho-so-thue-gtgt/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Công cụ Python tự đăng nhập Cổng Dịch vụ công của Cục Thuế
(`dichvucong.gdt.gov.vn`), nhận dạng CAPTCHA, tra cứu hồ sơ theo khoảng ngày và
tải về dạng ZIP kèm danh sách chi tiết để biết **loại tờ khai** của từng hồ sơ.

Chạy trên **Windows, Linux và macOS**, Python **3.10+**.

### Bộ công cụ họ Tải dữ liệu thuế điện tử của cùng tác giả

Cùng giải quyết bài toán **tự động hóa khai thác hệ thống thuế điện tử của
GDT** (đăng nhập CAPTCHA, tra cứu, tải về) nhưng mỗi công cụ nhắm một hệ
thống và một nền tảng:

| Công cụ | Nền tảng | Hệ thống GDT | Dữ liệu tải về |
|---|---|---|---|
| [**hddt-downloader-windows**](https://github.com/dieutx/hddt-downloader-windows) | PowerShell — Windows | `hoadondientu.gdt.gov.vn` (Hóa đơn điện tử) | XML hóa đơn mua vào/bán ra → Excel |
| **tai-ho-so-thue-gtgt** (repo này) | Python 3.10+ — Windows/Linux/macOS | `dichvucong.gdt.gov.vn` (Cổng Dịch vụ công, tự chuyển nguồn ETAX trước 01/07/2025 và trang Thuế điện tử cũ) | ZIP tờ khai + metadata CSV/JSON |
| [**TaiHoaDonDienTu**](https://github.com/dieutx/TaiHoaDonDienTu) | Excel VBA | `hoadondientu.gdt.gov.vn` (Hóa đơn điện tử) | XML hóa đơn → Excel |

Hai công cụ đầu dùng chung cách tiếp cận: tự nhận dạng CAPTCHA, tự đăng nhập,
chia nhỏ khoảng tra cứu theo giới hạn của hệ thống, retry/backoff khi bị giới
hạn tốc độ và lưu dữ liệu kèm danh sách chi tiết. Nếu bạn cần cả **hóa đơn**
và **tờ khai** thì có thể dùng song song hai công cụ này.

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Chức năng](#chức-năng)
- [Cài đặt](#cài-đặt)
- [Cấu hình](#cấu-hình)
- [Sử dụng](#sử-dụng)
- [Kết quả đầu ra](#kết-quả-đầu-ra)
- [Kiến trúc](#kiến-trúc)
- [Chọn bộ nhận dạng CAPTCHA](#chọn-bộ-nhận-dạng-captcha)
- [Benchmark](#benchmark)
- [Hiểu biết về cổng Dịch vụ công](#hiểu-biết-về-cổng-dịch-vụ-công)
- [Ghi log và lưu lại traffic](#ghi-log-và-lưu-lại-traffic)
- [Không bị nhận diện là Python](#không-bị-nhận-diện-là-python)
- [Dùng proxy (khi chạy ở nước ngoài)](#dùng-proxy-khi-chạy-ở-nước-ngoài)
- [Kiểm thử](#kiểm-thử)
- [Khắc phục sự cố](#khắc-phục-sự-cố)
- [Bảo trì khi cổng thay đổi](#bảo-trì-khi-cổng-thay-đổi)
- [Đóng góp](#đóng-góp)

---

## Tổng quan

Cổng Dịch vụ công của Cục Thuế chỉ cho tra cứu **tối đa 31 ngày mỗi lần**, dùng
CAPTCHA ở bước đăng nhập, và phân tách dữ liệu thành hai luồng tùy theo ngày nộp
hồ sơ. Công cụ này che hết những chi tiết đó:

```text
Khoảng ngày bất kỳ ──► tự cắt thành các đoạn ≤ 31 ngày
                   ──► tự chọn luồng ETAX (trước 01/07/2025) hoặc DVC (từ 01/07/2025)
                   ──► tự đọc CAPTCHA, tự thử lại khi đọc sai
                   ──► duyệt hết các trang, tải ZIP ngay trên từng trang
                   ──► lưu ZIP + CSV + JSON, bỏ qua hồ sơ đã tải
```

## Chức năng

- Tự chia khoảng tra cứu dài thành các đoạn **tối đa 31 ngày** — giới hạn của cổng.
- Tự chọn nguồn dữ liệu theo ngày nộp hồ sơ: **ETAX** trước `01/07/2025`,
  **DVC** từ `01/07/2025`. Cả hai đều bị chia nhỏ 31 ngày như nhau.
- **Nguồn dự phòng trang Thuế điện tử cũ** (`--legacy-etax`): một số tờ khai cũ
  chỉ còn hiển thị trên `thuedientu.gdt.gov.vn`, không tra cứu được qua cổng.
  Khi bật, đoạn ngày trước mốc mà cổng không trả hồ sơ nào sẽ được đăng nhập
  trang cũ (dùng chung tài khoản, tự đọc CAPTCHA) để tải bù dưới dạng XML.
- Xử lý đầy đủ phân trang và **tải ngay trên từng trang** để giữ trạng thái phiên.
- Nhận dạng CAPTCHA bằng **ddddocr** (mặc định); đổi được sang `easyocr`,
  `paddleocr`, `manual`, dịch vụ HTTP ngoài, hoặc solver tự viết.
- Đặt tên ZIP gợi nhớ: mã hồ sơ, kỳ tính thuế, **loại tờ khai**, tên tờ khai.
- Xuất `danh_sach_ho_so.csv` / `.json` kèm loại tờ khai, lần nộp, ngày nộp, trạng thái.
- Bỏ qua ZIP đã tải hợp lệ nên chạy tiếp được khi bị gián đoạn.
- Tự thử lại khi cổng trả `429 Too Many Requests` (đọc header `Retry-After`).
- `--dry-run` chỉ tra cứu, không tải file — dùng để kiểm tra khoảng ngày trước.
- **Gửi request như trình duyệt** (mặc định `--header-profile browser`): đủ
  `sec-ch-ua*`, `Sec-Fetch-*`, `Upgrade-Insecure-Requests`, `Accept` và thứ tự
  header như Chrome, khớp theo từng loại request — xem
  [Không bị nhận diện là Python](#không-bị-nhận-diện-là-python).
- **Log từng request**: một dòng cho mỗi request (phương thức, đường dẫn, tham số,
  mã trạng thái, thời gian, dung lượng) và chi tiết header/body ở mức `-v` hoặc
  trong file `--log-file`. Header/trường nhạy cảm được che bằng `***`.
- **`--dump-http`** lưu nguyên request/response ra file để dựng fixture khi cổng đổi.
- **`--header`** thêm hoặc ghi đè header cho mọi request ngay lúc chạy, không cần
  sửa mã nguồn.
- **`--proxy`** đẩy mọi request qua proxy Việt Nam — bắt buộc khi chạy trên VPS
  nước ngoài vì cổng chỉ phục vụ IP Việt Nam. Mật khẩu proxy luôn bị che trong log.

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

`requirements.txt` cài bộ nhận dạng mặc định `ddddocr` (~131MB cùng `onnxruntime`,
không cần `torch`). Muốn dùng solver khác thì xem
[Chọn bộ nhận dạng CAPTCHA](#chọn-bộ-nhận-dạng-captcha).

### Chỉ để chạy test

Test chạy hoàn toàn offline và **không cần** thư viện OCR nào:

```bash
pip install beautifulsoup4 lxml requests
python -m unittest discover -s tests -t . -v
```

### Cài như một gói

```bash
pip install -e .
gdt-tax --help
```

## Cấu hình

Sao chép `.env.example` thành `.env` rồi điền thông tin thật:

```dotenv
GDT_USERNAME=ma_so_thue-QL
GDT_PASSWORD=mat_khau_dich_vu_cong
GDT_FROM_DATE=01/01/2026
GDT_TO_DATE=31/01/2026
GDT_DOWNLOAD_DIR=download
```

**Thứ tự ưu tiên** (cao nhất trước): tham số dòng lệnh → biến môi trường → file `.env`.

File `.env` nằm trong `.gitignore`. Có thể chạy nhanh mà không sửa file:

```bash
GDT_FROM_DATE=01/01/2025 GDT_TO_DATE=31/01/2025 python -m gdt_tax
```

Bảng biến đầy đủ:

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
|---|---:|---|---|
| `GDT_USERNAME` | Có | — | Tên đăng nhập DVC Thuế (thường có hậu tố `-QL`) |
| `GDT_PASSWORD` | Có | — | Mật khẩu DVC Thuế |
| `GDT_FROM_DATE` | Không | `01/09/2026` | Ngày bắt đầu, `dd/mm/yyyy` |
| `GDT_TO_DATE` | Không | `25/09/2026` | Ngày kết thúc |
| `GDT_DOWNLOAD_DIR` | Không | `download` | Thư mục lưu ZIP và metadata |
| `GDT_CASE_ID` | Không | trống | Chỉ tải một mã hồ sơ |
| `GDT_CAPTCHA_SOLVER` | Không | `ddddocr` | `ddddocr`, `easyocr`, `paddleocr`, `manual`, `remote` |
| `GDT_CAPTCHA_OPTIONS` | Không | `{}` | Tham số solver, dạng JSON |
| `GDT_CAPTCHA_PLUGINS` | Không | trống | Đăng ký solver riêng: `ten=module:Lop` |
| `GDT_ETAX_CUTOFF` | Không | `01/07/2025` | Mốc chuyển giữa hai luồng dữ liệu |
| `GDT_MAX_DAYS_PER_SEARCH` | Không | `31` | Số ngày tối đa mỗi đoạn tra cứu |
| `GDT_PAGE_SIZE` | Không | `10` | Số hồ sơ mỗi trang |
| `GDT_LOGIN_ATTEMPTS` | Không | `10` | Số lần thử đăng nhập |
| `GDT_SEARCH_ATTEMPTS` | Không | `6` | Số lần thử lại một trang tra cứu |
| `GDT_REQUEST_TIMEOUT` | Không | `30` | Timeout mỗi request (giây) |
| `GDT_HTTP_RETRIES` | Không | `3` | Số lần thử lại khi gặp HTTP 429 |
| `GDT_PAUSE_BETWEEN_RECORDS` | Không | `1` | Nghỉ giữa 2 hồ sơ (giây) |
| `GDT_PAUSE_BETWEEN_PAGES` | Không | `3` | Nghỉ giữa 2 trang (giây) |
| `GDT_PAUSE_JITTER` | Không | `0.3` | Tỉ lệ ngẫu nhiên cộng thêm vào mỗi lần nghỉ (chỉ cộng, không rút ngắn) |
| `GDT_DRY_RUN` | Không | `false` | Chỉ tra cứu, không tải |
| `GDT_EXTRA_HEADERS` | Không | `{}` | Header thêm/ghi đè cho mọi request, dạng JSON |
| `GDT_HEADER_PROFILE` | Không | `browser` | `browser` (mặc định, gửi như Chrome) hoặc `minimal` (để loại trừ lỗi do header) |
| `GDT_PROXY_URL` | Không | trống | Proxy cho mọi request ra cổng, vd `1.2.3.4:8080:tai-khoan:mat-khau` |
| `GDT_LOG_FILE` | Không | trống | Ghi thêm toàn bộ log (mức DEBUG) ra file |
| `GDT_HTTP_DUMP_DIR` | Không | trống | Lưu nguyên request/response để dựng fixture |

## Sử dụng

Chạy từ thư mục gốc repo, hoặc dùng `gdt-tax` sau khi `pip install -e .`.

```bash
# Hồ sơ tháng 1/2025 (trước mốc 01/07/2025 → luồng ETAX), lưu riêng một thư mục
python -m gdt_tax --from-date 01/01/2025 --to-date 31/01/2025 --output-dir download/2025-01

# Hồ sơ tháng 1/2026 (từ mốc 01/07/2025 → luồng DVC)
python -m gdt_tax --from-date 01/01/2026 --to-date 31/01/2026 --output-dir download/2026-01

# Khoảng dài tùy ý: tự chia 31 ngày và tự chuyển luồng
python -m gdt_tax --from-date 01/01/2025 --to-date 31/12/2026

# Chỉ một hồ sơ
python -m gdt_tax --case-id 11320250292469209

# Chỉ tra cứu, không tải file
python -m gdt_tax --dry-run

# Bật nguồn dự phòng trang Thuế điện tử cũ (tờ khai cũ chỉ còn ở đó)
python -m gdt_tax --from-date 01/01/2020 --to-date 29/02/2020 --legacy-etax

# Tự nhập CAPTCHA (khi cổng đổi kiểu CAPTCHA)
python -m gdt_tax --solver manual

# Xem các bộ nhận dạng CAPTCHA có sẵn
python -m gdt_tax --list-solvers

# Ghi log chi tiết ra file và lưu lại traffic để chẩn đoán khi cổng đổi
python -m gdt_tax -v --log-file logs/run.log --dump-http http-dump

# Cổng yêu cầu thêm header mới: thêm ngay, không cần sửa mã nguồn
python -m gdt_tax --header "Referer=https://dichvucong.gdt.gov.vn/tthc/tchs"

# Loại trừ khả năng header gây lỗi (mặc định đã gửi y như Chrome)
python -m gdt_tax --header-profile minimal --dry-run

# Chạy trên máy chủ ngoài Việt Nam: đi qua proxy Việt Nam
python -m gdt_tax --proxy 1.2.3.4:8080:tai-khoan:mat-khau --dry-run
```

Mã thoát: `0` thành công, `1` chạy xong nhưng thiếu hồ sơ, `2` lỗi cấu hình.

## Kết quả đầu ra

```text
download/2025-01/
├── 11320250292469209__12-2024__Chinh-thuc__TO-KHAI-THUE-GIA-TRI-GIA-TANG-TT80-2021.zip
├── 11320250292528963__12-2024__Chinh-thuc__To-khai-khau-tru-thue-thu-nhap-ca-nhan-TT80.zip
├── danh_sach_ho_so.csv
└── danh_sach_ho_so.json
```

Tên ZIP gồm 4 phần, ngăn bằng `__`:
`<mã hồ sơ>__<kỳ tính thuế>__<loại tờ khai>__<tên tờ khai>.zip`.
Phần nào cổng không trả về (ví dụ kỳ tính thuế của thông báo hóa đơn lập sai) thì
thành `khong-ro`.

Mỗi dòng metadata gồm: mã hồ sơ, nguồn (`ETAX`/`DVC`), tên thủ tục hành chính,
tờ khai, kỳ tính thuế, **loại tờ khai**, lần nộp, lần bổ sung, ngày nộp, nơi nộp,
trạng thái, tên file ZIP. CSV ghi bằng UTF-8 kèm BOM để mở đúng trong Excel.

## Kiến trúc

Gói `gdt_tax` chia theo module một trách nhiệm; luồng chạy có 5 giai đoạn:

```text
cli ─► config ─► captcha (plugin)
  │
  └─► Pipeline.run()
        ├─ 1. login + mở trang hồ sơ        auth.py
        ├─ 2. chia đoạn tra cứu ≤ 31 ngày   dates.py
        ├─ 3. tra cứu từng trang, đọc bảng  portals/ + parsing.py
        ├─ 4. tải ZIP từng hồ sơ, lưu file  portals/ + storage.py
        └─ 5. xuất CSV/JSON                 storage.py
```

| Nhóm | Module |
|---|---|
| Nền tảng | `constants.py`, `models.py`, `errors.py` |
| Cấu hình & quy tắc ngày | `config.py`, `dates.py` |
| Hạ tầng | `http.py`, `proxy.py`, `csrf.py`, `parsing.py`, `naming.py`, `storage.py` |
| Header | `headers.py` — bộ header theo từng loại request, profile `browser` (mặc định) / `minimal` |
| Quan sát & gỡ lỗi | `traffic.py`, `logging_setup.py` |
| CAPTCHA (plugin) | `captcha/base.py`, `captcha/registry.py`, `captcha/*_solver.py` |
| Nguồn dữ liệu | `portals/base.py`, `portals/dvc.py`, `portals/etax.py` |
| Luồng & CLI | `auth.py`, `pipeline.py`, `cli.py`, `__main__.py` |

Chi tiết bảng endpoint, quy tắc phụ thuộc giữa module và cách thêm solver/portal
mới: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Chọn bộ nhận dạng CAPTCHA

```bash
python -m gdt_tax --list-solvers
# ddddocr   ← mặc định
# easyocr
# manual
# paddleocr
# remote
```

| Solver | Cần cài | Ghi chú |
|---|---|---|
| `ddddocr` | `ddddocr` + `onnxruntime` | Mặc định. ONNX, huấn luyện riêng cho CAPTCHA chữ-số |
| `easyocr` | `easyocr` + `torch` + `opencv-python-headless` + `numpy` | Tổng quát, nặng |
| `paddleocr` | `paddleocr` + `paddlepaddle` + `opencv-python-headless` + `numpy` | Tự nhận biết API 2.x và 3.x |
| `manual` | không | Lưu ảnh và hỏi người vận hành — dùng khi cổng đổi kiểu CAPTCHA |
| `remote` | không | Gọi một endpoint HTTP bên ngoài, không gắn cứng nhà cung cấp |

Đổi solver và truyền tham số riêng (JSON, chuyển thẳng thành tham số khởi tạo lớp solver):

```bash
# PaddleOCR
pip install "paddleocr>=2.7,<3" paddlepaddle opencv-python-headless numpy
export GDT_CAPTCHA_SOLVER=paddleocr
export GDT_CAPTCHA_OPTIONS='{"preprocess": true, "scale": 4}'

# Dịch vụ ngoài — chỉ cần một endpoint nhận ảnh và trả mã
export GDT_CAPTCHA_SOLVER=remote
export GDT_CAPTCHA_OPTIONS='{"url": "https://example.com/solve", "api_key": "...", "result_field": "data.text"}'

# Solver tự viết, đăng ký mà không cần sửa mã nguồn
export GDT_CAPTCHA_PLUGINS='myocr=goi_cua_toi.solver:MyOcrSolver'
export GDT_CAPTCHA_SOLVER=myocr
```

> **Cài chồng hai bộ OCR:** `ddddocr` cần `protobuf>=4.25` còn `paddlepaddle 2.6`
> chỉ nhận `<=3.20.2`. Dùng `protobuf==3.20.3` thì cả hai chạy được (đã kiểm chứng
> trên Windows, Python 3.12: cả `ddddocr` và `paddle` đều import và chạy).

## Benchmark

### Phương pháp đo

CAPTCHA của cổng là ảnh **150×38 px, 5 ký tự chữ-số**, dùng một lần và đổi mới
mỗi lần gọi. Vì vậy mọi con số đều phải đo trên **CAPTCHA thật do cổng phát ra**,
không thể đo trên ảnh lưu sẵn (không có nhãn đúng).

**Môi trường đo:** Windows 11 (build 22631, Git Bash) · Python 3.12.4 ·
Intel Core thế hệ 10, 12 luồng CPU · chạy CPU-only, không dùng GPU ·
một tài khoản doanh nghiệp · ngày đo 25/09/2026 ·
`onnxruntime 1.30.0` · `easyocr 1.7.2` + `torch 2.14.0+cpu` · `paddleocr 2.7.3` +
`paddlepaddle 2.6.2`.

**Phép đo 1 — độ chính xác CAPTCHA đăng nhập.** Đăng nhập một lần để lấy phiên,
sau đó lặp N lần: lấy CAPTCHA mới → đọc → gửi lên `/tthc/loginLDAP` → đọc trường
`status` trong phản hồi (`200` = mã đúng, `999` = "Mã captcha không đúng"). Đo ở
bước đăng nhập vì đó là nơi duy nhất cổng thực sự kiểm CAPTCHA (xem
[mục dưới](#hiểu-biết-về-cổng-dịch-vụ-công)). N = 6 mỗi solver.

**Phép đo 2 — đọc được, chạy offline.** Chạy từng solver trên 22 ảnh CAPTCHA cũ
do cổng phát ra, chỉ đếm xem solver có trả về **đúng 5 ký tự chữ-số** hay không.
Không có nhãn đúng nên phép đo này **không** nói solver nào đọc *đúng*.

**Phép đo 3 — thời gian chạy đầu cuối.** Chạy thật cùng một tháng, cùng số hồ sơ,
mỗi lần là một tiến trình mới; số liệu gồm cả độ trễ mạng tới cổng.

### Kết quả

**CAPTCHA đăng nhập (N = 6 mỗi solver):**

| Solver | Đọc đúng | Thời gian/ảnh | Ghi chú |
|---|---|---|---|
| **`ddddocr`** | **6/6** | **0,06s** | Mặc định |
| `paddleocr` | 3/6 | 0,60s | |
| `easyocr` | 2/6 | 3,14s | Chậm gấp ~52 lần ddddocr |

**Đọc được offline (22 ảnh lưu sẵn):**

| Solver | Trả về đúng 5 ký tự | Thời gian/ảnh |
|---|---|---|
| `ddddocr` | 22/22 | 0,01s |
| `easyocr` | 21/22 | ~2,5s |
| `paddleocr` | 17/22 | 0,05s |

**Thời gian chạy đầu cuối:**

| Tháng | Hồ sơ | `easyocr` | `ddddocr` |
|---|---:|---:|---:|
| 01/2025 | 2 | 32s | 5s |
| 01/2026 | 6 | 23s | 8s |

Số liệu `easyocr` gồm thời gian nạp mô hình (~10s mỗi tiến trình) và việc phải
thử đăng nhập nhiều lần; `ddddocr` thường đăng nhập thành công ngay lần đầu.

**Dung lượng phụ thuộc** (đo bằng `du -sm` trên máy đo, chỉ tính thư viện đặc thù):

| Solver | Thành phần | Tổng |
|---|---|---:|
| `ddddocr` | `ddddocr` 85MB + `onnxruntime` 46MB | ~131MB |
| `paddleocr` | `paddle` 299MB + `paddleocr` 5MB | ~304MB |
| `easyocr` | `torch` 539MB + `easyocr` 16MB | ~555MB |

### Giới hạn của các số liệu này

Nêu rõ để không đọc quá mức kết quả:

- **Cỡ mẫu nhỏ.** Với 6/6, khoảng tin cậy 95% (Clopper–Pearson) chỉ kết luận được
  độ chính xác thực **≥ ~61%**, không phải 100%. Với 2/6, khoảng tin cậy là
  ~4%–78%. Muốn kết luận chắc chắn nên đo từ 20–30 lần mỗi solver.
- **Chỉ một tài khoản, một khu vực, một thời điểm.** CAPTCHA của cổng có thể khác
  nhau giữa các khu vực hoặc sau khi cổng nâng cấp.
- **Phép đo offline không có nhãn**, nên chỉ đo khả năng "đọc ra 5 ký tự".
- **Thời gian gồm độ trễ mạng** tới cổng thuế, dao động theo giờ.
- CAPTCHA là biến ngẫu nhiên: chiến lược đúng của công cụ là **thử lại với ảnh
  mới**, không phải kỳ vọng đọc đúng 100%.

Cách tự kiểm chứng: giữ nguyên quy trình ở *Phương pháp đo* (script đo không được
đưa vào repo vì nó gửi request đăng nhập thật).

## Hiểu biết về cổng Dịch vụ công

Những điều dưới đây đã được **kiểm chứng trực tiếp** trên cổng, ghi lại để người
sau không phải dò lại. Đây cũng là lý do các quyết định thiết kế trong mã nguồn.

**Tra cứu và dữ liệu**

1. **Giới hạn 31 ngày áp dụng cho cả hai luồng**, kể cả ETAX trước `01/07/2025`.
   Đoạn tra cứu ETAX còn bị chặn không vượt qua mốc `01/07/2025`.
2. **Mốc `01/07/2025` tách hai luồng dữ liệu** với endpoint, tham số và cách đặt
   mã hồ sơ khác nhau: ETAX dùng mã số dạng `1132025…`, DVC dùng dạng
   `G12.18-YYMMDD-…` (kèm tiền tố `000.101.18.` khi tải).
3. **Phải tải ngay trong lúc phân trang.** Cổng chỉ giữ danh sách hồ sơ của trang
   tra cứu gần nhất trong phiên; gom hết mã hồ sơ rồi mới tải sẽ bị từ chối với
   lỗi `validateIdTkhai`.
4. **Hai luồng trả bảng kết quả khác số cột** (ETAX 11 cột, DVC 13 cột) và thứ tự
   cột khác nhau — xem đầu `gdt_tax/parsing.py`.
5. **Một số hồ sơ không có kỳ tính thuế** (ví dụ thông báo hóa đơn điện tử lập sai
   mẫu `04/SS-HĐĐT`). Xử lý đúng là để trống và ghi `khong-ro`, không phải bỏ hồ sơ.

**CAPTCHA**

6. **Cổng chỉ kiểm CAPTCHA ở bước đăng nhập.** Gửi CAPTCHA sai (`00000`), vô nghĩa
   (`zzzzz`) hoặc **rỗng** tới `GET /tthc/ho-so/search` vẫn nhận đủ kết quả của
   trang tra cứu. Vì vậy chỉ cần tối ưu độ chính xác CAPTCHA cho `login()`.
7. **CAPTCHA là ảnh 150×38 px, 5 ký tự chữ-số, dùng một lần.** Sai thì cổng trả
   `status = 999` kèm mô tả `"Mã captcha không đúng, vui lòng thử lại."` — phân
   biệt được với sai mật khẩu.
8. **Cổng đọc CAPTCHA phân biệt chữ hoa/thường và phân biệt `O`/`0`, `I`/`1`.**
   Một số bộ OCR trả `Itkmg` khi đáp án là `1tkmg`; sai kiểu này vẫn bị từ chối.

**Giao thức và định dạng**

9. **Mật khẩu được gửi đã mã hoá Base64** trong trường `matKhau` của
   `POST /tthc/loginLDAP` (chỉ là định dạng truyền, không phải bảo mật).
10. **CSRF token nằm ở hai chỗ khác nhau**: thẻ `<meta name="csrf-token">` ở trang
    đăng nhập, và ô ẩn `<input name="_csrf">` ở trang chi tiết hồ sơ.
11. **ZIP có lúc trả về nhị phân, có lúc trả Base64 trong JSON** (`{"content": "…"}`,
    kèm `fileName`). Phải thử cả hai đường và luôn kiểm tra archive bằng
    `ZipFile.testzip()` trước khi lưu.
12. **Tải hồ sơ DVC đi qua một bước kiểm tra AJAX** (`GET /tthc/tchs/validateIdTkhai`,
    trả về đúng chuỗi `200`). Khi cổng tắt bước này, cần đường lui bằng form
    `POST /tthc/downloadhoso` — công cụ đã có sẵn.
13. **Cổng trả `429 Too Many Requests`** khi tra cứu quá nhanh. Cách xử lý đúng là
    đọc header `Retry-After` và chờ, không phải thử lại ngay.

**Chi tiết nhỏ dễ bỏ sót**

14. **Chữ `đ` (U+0111) không tách được bằng NFKD**, nên bỏ dấu theo cách thông
    thường sẽ cho `Hoat-ong` thay vì `Hoat-dong`. Phải thay `đ` → `d` trước khi
    chuẩn hoá.
15. **`str.isalnum()` của Python coi chữ có dấu tiếng Việt là hợp lệ**, nên dùng nó
    để lọc kết quả OCR là sai; phải dùng regex ASCII `[A-Za-z0-9]`.
16. **Tên file ZIP nên bất biến theo nội dung**: đặt tên theo mã hồ sơ, kỳ tính
    thuế và loại tờ khai giúp lần chạy sau nhận ra file đã tải và bỏ qua.
17. **Gửi header giống Chrome thì phải đúng cả bộ, đúng thứ tự, và đừng khai
    `zstd`.** Cổng không kiểm dấu vân tay trình duyệt (nó chỉ giới hạn ở tầng ứng
    dụng bằng 429 và kiểm CAPTCHA ở bước đăng nhập), nhưng mục tiêu của công cụ là
    không để lộ ra là Python. Vài điều đã do và kiểm chứng:
    - **`Accept-Encoding`**: Chrome gửi `gzip, deflate, br, zstd`, nhưng `zstd`
      **dùng không được**: urllib3 (tới 2.8) chỉ giải mã `gzip`, `deflate`, `br`,
      `x-gzip`. Đo thật: cài `zstandard` rồi gửi `Accept-Encoding: zstd` thì
      `response.content` vẫn là byte nén ⇒ ZIP tải về sẽ hỏng. Vì vậy công cụ chỉ
      khai `br` khi có `brotli`, và **không bao giờ** khai `zstd` — xem
      `accept_encoding()` trong `gdt_tax/headers.py`.
    - **Thứ tự header cũng là một dấu hiệu.** `requests` gộp header của `Session`
      lên trước và giữ nguyên vị trí của khoá đã có, nên chỉ sắp xếp trong từng
      builder là chưa đủ; `HttpClient` phải xoá header mặc định của session rồi sắp
      lại bộ cuối cùng. `Host` và `Content-Length` do urllib3 đặt nên vẫn lệch.
    - **Đừng thêm `Sec-Fetch-*` hay `sec-ch-ua*` bằng tay**: giá trị phụ thuộc loại
      request, và `sec-ch-ua` phải khớp `Chrome/<số>` với `User-Agent` — sai một
      trường là dấu hiệu lạ còn rõ hơn là không có. Header nào cần thêm thì sửa
      `gdt_tax/headers.py` rồi chạy `tests/test_headers.py`.
    - Muốn thử một header mới mà chưa sửa code: `--header`/`GDT_EXTRA_HEADERS`.
    - Muốn thấy đúng những gì đã gửi: `--dump-http` (xem mục
      [Ghi log và lưu lại traffic](#ghi-log-và-lưu-lại-traffic)).

## Ghi log và lưu lại traffic

Cổng Dịch vụ công có thể đổi giao diện bất cứ lúc nào, và khi đó người sửa cần
đúng dữ liệu thật của cổng. Chương trình có sẵn ba mức quan sát, dùng tăng dần:

**1. Mặc định — một dòng cho mỗi request.**

```text
10:35:28 [INFO] gdt_tax.http: HTTP GET https://dichvucong.gdt.gov.vn/tthc/ho-so/search?tuNgay=01/01/2026&denNgay=31/01/2026&page=1 → 200 (1.02s, 12.4 kB)
```

**2. `-v` — thêm header, tham số và body đã cắt bớt.**

```text
10:35:28 [DEBUG] gdt_tax.http: GỬI POST https://dichvucong.gdt.gov.vn/tthc/loginLDAP (lần 1/10)
10:35:28 [DEBUG] gdt_tax.http:   header: {'User-Agent': 'Mozilla/5.0 ...', 'Cookie': '***', 'X-XSRF-TOKEN': '***'}
10:35:28 [DEBUG] gdt_tax.http:   body: {"tenDN": "0101234567-QL", "matKhau": "***", "captcha": "abcde"}
10:35:28 [DEBUG] gdt_tax.http:   ← header: {'Content-Type': 'application/json', 'Set-Cookie': '***'}
10:35:28 [DEBUG] gdt_tax.http:   ← body: {"status": "200"}
```

**3. `--log-file` — lưu toàn bộ log ở mức `DEBUG` vào file**, kể cả khi màn hình
chỉ hiện `INFO`. File này đủ để gửi kèm khi báo lỗi:

```bash
python -m gdt_tax --log-file logs/run.log        # màn hình gọn, file đầy đủ
python -m gdt_tax -v --log-file logs/run.log     # cả hai đều chi tiết
```

**4. `--dump-http` — lưu nguyên request/response ra file**, để dựng lại fixture
khi cổng đổi giao diện:

```bash
python -m gdt_tax --dry-run --dump-http http-dump
```

```text
http-dump/20260925-103528/
├── 0001-GET-login.request.txt          phương thức, URL, tham số, header, body
├── 0001-GET-login.response.txt         mã trạng thái, thời gian, header, body
├── 0001-GET-login.response.body        body nguyên bản (nhị phân)
├── 0002-GET-ho-so-search.request.txt
└── ...
```

Mỗi lần chạy tạo một thư mục con theo thời điểm bắt đầu nên không ghi đè kết quả
cũ. File `.response.body` giữ nguyên byte gốc; file `.response.txt` để đọc bằng
mắt. Mỗi file bị giới hạn **2 MB** để một trang lớn không làm đầy đĩa.

Báo lỗi khi cổng đổi giao diện nhanh nhất là: cắt phần response tương ứng thành
fixture (nhớ che mã số thuế, mã hồ sơ), thêm vào `tests/fixtures/`, chạy test để
thấy chỗ vỡ.

**Thêm hoặc ghi đè header lúc chạy.** Khi cổng yêu cầu một header mới, thử ngay
không cần sửa mã:

```bash
python -m gdt_tax --header "X-Requested-With=XMLHttpRequest" --header "Referer: https://dichvucong.gdt.gov.vn/tthc/tchs"
GDT_EXTRA_HEADERS='{"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}' python -m gdt_tax
```

Header cấu hình **thắng** header mà portal tự đặt, nên ghi đè được `User-Agent`,
`Referer`... Nếu cách này chạy tốt lâu dài thì chuyển giá trị đó vào
`DEFAULT_HEADERS` trong `gdt_tax/constants.py`.

> **Dữ liệu nhạy cảm luôn được che.** `Cookie`, `Set-Cookie`, `Authorization`,
> `X-XSRF-TOKEN` trong header và `matKhau`, `_csrf`, `password`, `token` trong body
> đều thành `***` trước khi ghi ra log hay file dump. Cảnh giác vẫn nên có: nội
> dung HTML của cổng có thể chứa mã số thuế và mã hồ sơ của bạn.

## Dùng proxy (khi chạy ở nước ngoài)

Cổng Dịch vụ công chỉ phục vụ IP Việt Nam. Đo thật từ máy ở Đức: `GET
https://dichvucong.gdt.gov.vn/tthc/login` bị chặn ngay ở tầng kết nối (`Max retries
exceeded`); cùng request đó qua một proxy Hà Nội trả `HTTP 200`, 66,9 KB kèm thẻ
CSRF — tức là toàn bộ luồng chạy được. Nếu bạn chạy trên VPS/máy chủ ngoài Việt
Nam thì **phải dùng proxy Việt Nam**.

```bash
# Dạng nhiều nhà cung cấp VN hay đưa: host:port:tài-khoản:mật-khẩu
python -m gdt_tax --proxy 1.2.3.4:8080:tai-khoan:mat-khau

# URL đầy đủ, hoặc SOCKS (cần pip install "requests[socks]")
python -m gdt_tax --proxy "http://tai-khoan:mat-khau@1.2.3.4:8080"
python -m gdt_tax --proxy "socks5://tai-khoan:mat-khau@1.2.3.4:1080"

# Hoặc ghi một lần vào .env (đã nằm trong .gitignore) cho khỏi gõ lại
GDT_PROXY_URL=1.2.3.4:8080:tai-khoan:mat-khau
```

Các dạng chuỗi được nhận:

| Dạng | Ví dụ |
|---|---|
| `host:port` (không cần tài khoản) | `1.2.3.4:8080` |
| `host:port:tài-khoản:mật-khẩu` | `1.2.3.4:8080:muaproxy:matkhau` |
| `tài-khoản:mật-khẩu@host:port` (mặc định `http`) | `muaproxy:matkhau@1.2.3.4:8080` |
| URL đầy đủ `http`/`https`/`socks*` | `http://muaproxy:matkhau@1.2.3.4:8080` |

Mật khẩu chứa `@`, `:` hay `/` vẫn dùng được: tài khoản được percent-encode khi
dựng lại URL, và dạng `host:port:tài-khoản:mật-khẩu` được ưu tiên khi trường thứ
hai là port hợp lệ.

**An toàn khi dùng proxy:**

- Proxy áp dụng cho **mọi** request ra cổng: mở trang đăng nhập, CAPTCHA, tra cứu,
  trang chi tiết và tải ZIP đều đi chung một đường. Riêng solver CAPTCHA `remote`
  gọi dịch vụ ngoài nên vẫn đi trực tiếp.
- **Mật khẩu proxy không bao giờ vào log.** `SecretsFilter` che ở mọi handler — kể
  cả log của `urllib3`, vốn in cả URL proxy kèm tài khoản — và `--dump-http` cũng
  không ghi proxy. Bạn vẫn không nên dán `GDT_PROXY_URL` vào issue hay PR.
- Lỗi proxy được đổi thành một dòng `NetworkError` (đã che mật khẩu) kèm gợi ý,
  thay vì traceback dài.
- Kiểm tra proxy bằng tay: `curl -x http://user:pass@1.2.3.4:8080 https://ipinfo.io/json`
  phải trả `"country": "VN"`.

## Không bị nhận diện là Python

Mục tiêu: request gửi lên cổng không bị phân biệt được với request của người dùng
đang đăng nhập bằng trình duyệt. Công cụ làm được điều đó ở tầng HTTP, và nói thẳng
chỗ không làm được ở tầng vận chuyển.

**Đang mô phỏng đúng** — mặc định `GDT_HEADER_PROFILE=browser`:

| Dấu hiệu | Gửi đi | Ghi chú |
|---|---|---|
| `User-Agent` | Chrome/153 trên Windows | khai trong `constants.py`, nên đổi theo Chrome bạn đang dùng |
| `sec-ch-ua*` | khớp `User-Agent` | tự tính; ghi đè `User-Agent` thì hint tính lại, không phải Chrome thì bỏ hẳn |
| `Sec-Fetch-Site/Mode/User/Dest` | đúng theo loại request | mở trang `document`/`navigate`, AJAX `empty`/`cors`, ảnh CAPTCHA `image`/`no-cors` |
| `Upgrade-Insecure-Requests` | `1` | chỉ ở request mở trang |
| `Accept` | chuỗi dài như Chrome | HTML khi mở trang, danh sách `image/...` cho CAPTCHA, `*/*` cho AJAX |
| `Accept-Encoding` | `gzip, deflate, br` | `zstd` không dùng được (mục 17 ở trên); `pip install brotli` thì khớp Chrome hơn hẳn |
| `Referer` | bỏ ở điều hướng đầu tiên | giữ nhất quán với `Sec-Fetch-Site: none` |
| Thứ tự header | theo Chrome | trừ `Host`, `Content-Length` do urllib3 đặt |
| Nhịp thời gian | nghỉ ngẫu nhiên, **chỉ cộng thêm** | `GDT_PAUSE_JITTER`, mặc định `0.3` (0–30%) |
| `Cookie`, `Origin`, `X-Requested-With`, `HX-*` | như browser/HTMX thật | bám theo luồng quan sát được trên cổng |

**Không sửa được bằng header** — biết trước để không kỳ vọng sai:

- **HTTP/2**: browser thật thương lượng HTTP/2 qua ALPN trong TLS; `requests`/
  `urllib3` chỉ nói HTTP/1.1. WAF nào đọc ALPN sẽ thấy khác.
- **Dấu vân tay TLS (JA3/JA4)**: ClientHello của urllib3 khác Chrome.

Hai điểm này chỉ giải quyết được bằng cách đổi lớp vận chuyển (`curl_cffi` với
`impersonate="chrome"`, hoặc `httpx[http2]`). `HttpClient` là **nơi duy nhất** gọi
mạng, nên khi cần chỉ phải thay lớp đó — portal, parsing, storage không đổi.
Cổng thuế hiện chỉ giới hạn ở tầng ứng dụng nên hai điểm trên chưa thành vấn đề.

Nghi ngờ chính header gây lỗi thì chạy lại với profile tối thiểu; đây cũng là cách
loại trừ nhanh khi có sự cố:

```bash
GDT_HEADER_PROFILE=minimal python -m gdt_tax --dry-run
```

## Kiểm thử

```bash
python -m unittest discover -s tests -t . -v   # 257 test, chạy offline
ruff check .                                   # lint
mypy gdt_tax                                   # kiểm tra kiểu (32 file)
```

Bộ test **không cần Internet và không cần tài khoản**: `tests/support.py` cung cấp
`FakeHttp` định tuyến theo `(method, đường dẫn)`, nên `test_pipeline.py` chạy
nguyên 5 giai đoạn với phản hồi dựng sẵn.

| File | Nội dung |
|---|---|
| `test_dates.py` | Chia 31 ngày, mốc ETAX, các trường hợp biên và lỗi đầu vào |
| `test_parsing.py` | Đọc bảng ETAX/DVC từ fixture HTML thật, bỏ trùng, hàng thiếu cột |
| `test_naming.py` | Tên file ZIP, có test riêng cho chữ `đ` |
| `test_config.py` | Ưu tiên cấu hình, kiểm tra kiểu, lỗi thiếu tài khoản |
| `test_http.py` | Ghép URL, thử lại khi 429, `Retry-After` sai định dạng, log request, header ghi đè, dump |
| `test_headers.py` | Bộ header theo profile và theo loại request, client hint khớp `User-Agent`, `Accept-Encoding` không khai `zstd` |
| `test_traffic.py` | Che header/body nhạy cảm, định dạng log, ghi file dump và giới hạn dung lượng |
| `test_logging_setup.py` | Mức log ra màn hình so với file log, che bí mật trong log, `SecretsFilter` che mật khẩu proxy kể cả trong log của urllib3 |
| `test_proxy.py` | Đọc các dạng chuỗi proxy, che mật khẩu, và request đi qua proxy thật (proxy giả tại chỗ) |
| `test_storage.py` | ZIP hợp lệ/hỏng, giải mã Base64, bỏ qua file đã có, CSV/JSON |
| `test_captcha.py` | Sổ đăng ký solver, nạp muộn, `normalize_text` |
| `test_captcha_backends.py` | Smoke test từng backend OCR, tự bỏ qua nếu chưa cài thư viện |
| `test_pipeline.py` | Chạy đầu cuối với HTTP giả: ETAX, DVC, phân trang, `--dry-run`, `--case-id`, lỗi |
| `test_cli.py` | Tham số dòng lệnh, mã thoát, danh sách solver |

Fixture HTML được rút gọn từ trang thật và đã bỏ mã số thuế, mã hồ sơ. Khi cổng
đổi giao diện, cách sửa nhanh nhất là thay fixture rồi chạy test để thấy chỗ vỡ;
dùng `--dump-http` để lấy lại HTML thật cần thiết.

## Khắc phục sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ĐĂNG NHẬP THẤT BẠI` sau 10 lần | Sai tài khoản/mật khẩu, hoặc CAPTCHA không đọc được | Kiểm tra `GDT_USERNAME` (đúng dạng `ma_so_thue-QL`); thử `--solver manual` để loại trừ OCR |
| Log ghi `OCR không đọc được` liên tục | Solver không hợp với ảnh hiện tại | Đổi solver hoặc dùng `--solver manual` |
| Tra cứu trả `records=0` mãi | Khoảng ngày không có hồ sơ, hoặc sai định dạng ngày | Thử `--dry-run`, kiểm tra `dd/mm/yyyy` |
| Máy chủ giới hạn tần suất (429) | Tra cứu quá nhanh | Tăng `GDT_PAUSE_BETWEEN_RECORDS` / `GDT_PAUSE_BETWEEN_PAGES` |
| Tên file có `khong-ro` | Hồ sơ không có kỳ tính thuế (ví dụ mẫu `04/SS-HĐĐT`) | Bình thường, không phải lỗi |
| Không tải lại file đã xoá nội dung | File ZIP cũ vẫn hợp lệ nên bị bỏ qua | Xoá file cũ hoặc dùng thư mục `--output-dir` khác |
| `ModuleNotFoundError: ddddocr` | Chưa cài bộ nhận dạng | `pip install ddddocr onnxruntime`, hoặc `--solver manual` |
| `paddle` lỗi `protobuf` | Cài chồng `ddddocr` và `paddlepaddle` | `pip install "protobuf==3.20.3"` |
| Cổng trả lỗi lạ, cần xem request thật | Cổng đổi tham số/header | `-v`, hoặc `--log-file logs/run.log --dump-http http-dump` |
| Cổng đòi header mới | Cổng nâng cấp giao diện | `--header "Tên=Giá trị"` để thử ngay |
| Lỗi kết nối / `Max retries exceeded` khi chạy trên VPS nước ngoài | Cổng chỉ phục vụ IP Việt Nam | Dùng `--proxy`/`GDT_PROXY_URL` với proxy Việt Nam |
| `ProxyError`, proxy hết hạn hoặc sai tài khoản | Cấu hình proxy sai | Kiểm tra `GDT_PROXY_URL`; thử bằng `curl -x … https://ipinfo.io/json`; hoặc bỏ proxy để đi trực tiếp |
| Log hiện `***` ở địa chỉ proxy | `SecretsFilter` che tài khoản proxy | Bình thường, cố ý |
| Nghi header gây lỗi | Một header mới không hợp với cổng | `GDT_HEADER_PROFILE=minimal` để loại trừ, rồi báo lại để sửa `headers.py` |
| Muốn xem log của lần chạy trước | Log chỉ in ra màn hình | Chạy lại với `--log-file`; file log được ghi thêm, không xoá lần trước |

## Bảo trì khi cổng thay đổi

Cổng có thể đổi bất cứ lúc nào. Bản đồ sửa nhanh:

| Cổng thay đổi gì | Sửa ở đâu |
|---|---|
| Khoảng ngày trả về rỗng, cần xem request thật | `--log-file logs/run.log --dump-http http-dump` rồi đối chiếu |
| Cổng yêu cầu thêm header | Thử `--header "Tên=Giá trị"`, chạy ổn định rồi mới thêm vào `gdt_tax/headers.py` |
| Cổng chặn theo dấu hiệu trình duyệt (403, trang chặn) | Gửi như browser là mặc định rồi; nếu vẫn bị chặn thì thường là do TLS/HTTP2 — phải đổi lớp vận chuyển, xem mục [Không bị nhận diện là Python](#không-bị-nhận-diện-là-python) |
| HTML bảng kết quả | Cập nhật `tests/fixtures/*.html` rồi `gdt_tax/parsing.py` |
| Địa chỉ hoặc tên tham số endpoint | `gdt_tax/constants.py` |
| Cách gọi endpoint tải ZIP | Portal tương ứng trong `gdt_tax/portals/` |
| Kiểu CAPTCHA | Thêm/chọn solver trong `gdt_tax/captcha/` |
| Mốc `01/07/2025` | `GDT_ETAX_CUTOFF` hoặc `ETAX_CUTOFF_DEFAULT` trong `dates.py` |
| Giới hạn số ngày mỗi lần tra cứu | `GDT_MAX_DAYS_PER_SEARCH` hoặc `MAX_DAYS_PER_SEARCH_DEFAULT` |

Sau khi sửa, chạy lại `python -m unittest discover -s tests -t . -v` và kiểm chứng
bằng `--dry-run` trước khi tải thật.

## Đóng góp

Xem [CONTRIBUTING.md](CONTRIBUTING.md) để biết cách cài môi trường, chạy test, quy
ước commit và chuẩn cho một bộ nhận dạng CAPTCHA mới.

## Giấy phép và miễn trừ

Phát hành theo [giấy phép MIT](LICENSE).

- Chỉ dùng với **tài khoản và hồ sơ mà bạn có quyền truy cập**.
- Không commit tài khoản, mật khẩu, cookie hay CSRF token vào repository.
- Đây là công cụ cá nhân, không phải sản phẩm chính thức của cơ quan thuế.
