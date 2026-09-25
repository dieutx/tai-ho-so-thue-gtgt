# Tải hồ sơ thuế GTGT từ Cổng Dịch vụ công

[![CI](https://github.com/dieutx/tai-ho-so-thue-gtgt/actions/workflows/ci.yml/badge.svg)](https://github.com/dieutx/tai-ho-so-thue-gtgt/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Công cụ Python tự đăng nhập Cổng Dịch vụ công của Cục Thuế
(`dichvucong.gdt.gov.vn`), nhận dạng CAPTCHA, tra cứu hồ sơ theo khoảng ngày và
tải về dạng ZIP kèm danh sách chi tiết để biết **loại tờ khai** của từng hồ sơ.

Chạy trên **Windows, Linux và macOS**, Python **3.10+**.

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
- Xử lý đầy đủ phân trang và **tải ngay trên từng trang** để giữ trạng thái phiên.
- Nhận dạng CAPTCHA bằng **ddddocr** (mặc định); đổi được sang `easyocr`,
  `paddleocr`, `manual`, dịch vụ HTTP ngoài, hoặc solver tự viết.
- Đặt tên ZIP gợi nhớ: mã hồ sơ, kỳ tính thuế, **loại tờ khai**, tên tờ khai.
- Xuất `danh_sach_ho_so.csv` / `.json` kèm loại tờ khai, lần nộp, ngày nộp, trạng thái.
- Bỏ qua ZIP đã tải hợp lệ nên chạy tiếp được khi bị gián đoạn.
- Tự thử lại khi cổng trả `429 Too Many Requests` (đọc header `Retry-After`).
- `--dry-run` chỉ tra cứu, không tải file — dùng để kiểm tra khoảng ngày trước.

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
| `GDT_DRY_RUN` | Không | `false` | Chỉ tra cứu, không tải |

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

# Tự nhập CAPTCHA (khi cổng đổi kiểu CAPTCHA)
python -m gdt_tax --solver manual

# Xem các bộ nhận dạng CAPTCHA có sẵn
python -m gdt_tax --list-solvers
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
| Hạ tầng | `http.py`, `csrf.py`, `parsing.py`, `naming.py`, `storage.py` |
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

## Kiểm thử

```bash
python -m unittest discover -s tests -t . -v   # 114 test, chạy offline
ruff check .                                   # lint
mypy gdt_tax                                   # kiểm tra kiểu (29 file)
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
| `test_http.py` | Ghép URL, thử lại khi 429, `Retry-After` sai định dạng |
| `test_storage.py` | ZIP hợp lệ/hỏng, giải mã Base64, bỏ qua file đã có, CSV/JSON |
| `test_captcha.py` | Sổ đăng ký solver, nạp muộn, `normalize_text` |
| `test_captcha_backends.py` | Smoke test từng backend OCR, tự bỏ qua nếu chưa cài thư viện |
| `test_pipeline.py` | Chạy đầu cuối với HTTP giả: ETAX, DVC, phân trang, `--dry-run`, `--case-id`, lỗi |
| `test_cli.py` | Tham số dòng lệnh, mã thoát, danh sách solver |

Fixture HTML được rút gọn từ trang thật và đã bỏ mã số thuế, mã hồ sơ. Khi cổng
đổi giao diện, cách sửa nhanh nhất là thay fixture rồi chạy test để thấy chỗ vỡ.

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

## Bảo trì khi cổng thay đổi

Cổng có thể đổi bất cứ lúc nào. Bản đồ sửa nhanh:

| Cổng thay đổi gì | Sửa ở đâu |
|---|---|
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
