# Đóng góp

Cảm ơn bạn muốn cải thiện công cụ này. Tài liệu ngắn gọn dưới đây giúp bạn chạy
dự án và gửi thay đổi nhanh.

## Chuẩn bị môi trường

Nếu tiếp tục công việc trên máy khác, đọc
[bàn giao](docs/development/HANDOFF.md) và [trạng thái stage](docs/development/README.md)
trước; chỉ làm phần còn thiếu. Tạo lại venv, không copy môi trường từ máy cũ.

```bash
git clone https://github.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
python -m venv .venv
```

Kích hoạt môi trường (Windows: `.\.venv\Scripts\Activate.ps1`, Linux:
`source .venv/bin/activate`) rồi cài:

```bash
python -m pip install -e ".[dev]"
```

Lệnh trên cài package, thư viện chính, Ruff và mypy. Test offline không cần tài
khoản hoặc thư viện OCR. Chỉ cài thêm OCR khi cần kiểm tra backend tương ứng:

```bash
python -m pip install -e ".[dev,ocr-ddddocr]"
```

## Chạy test

```bash
python -m unittest discover -s tests -t . -v
python -m ruff check .
python -m mypy gdt_tax
```

Test phải xanh trước khi mở pull request — CI trên GitHub Actions chạy đúng các lệnh ở
trên trên Linux; nếu bạn sửa code liên quan tới Windows thì chạy thử thêm trên
Windows trước khi mở PR.

## Chuẩn cho một bộ nhận dạng CAPTCHA mới

Trước khi đề xuất đổi mặc định, hãy đo và ghi lại số liệu: đăng nhập một lần,
sau đó N lần "lấy CAPTCHA mới → đọc → gửi lên cổng", đếm số lần cổng trả
`status = 200`. Cỡ mẫu nên từ 20 lần
trở lên nếu muốn kết luận chắc chắn; mọi kết quả đều phải kèm ngày đo, hệ điều
hành, phiên bản Python và phiên bản thư viện.

Solver mới cần: kế thừa `CaptchaSolver`, trả về `""` khi không đọc chắc chắn,
không import thư viện nặng ở cấp module, và có test bỏ qua được khi thư viện chưa
cài (xem `tests/test_captcha_backends.py`).

## Nguyên tắc viết mã

- Mỗi module một trách nhiệm. Xem bảng ở [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Không import `easyocr`/`torch` ở cấp module; chỉ import bên trong hàm để giữ
  cho `import gdt_tax` nhẹ và test chạy không cần OCR.
- Thay đổi giao diện cổng thì sửa `constants.py`, `parsing.py` hoặc portal — không
  rải điều kiện rẽ nhánh khắp nơi.
- Không tự ghép dict header trong portal/auth: mọi header đi qua
  `gdt_tax/headers.py` (một builder cho mỗi loại request). Sửa header là sửa ở đó
  rồi chạy `tests/test_headers.py`; đừng khai `Accept-Encoding` bằng tay, xem
  `accept_encoding()` để biết vì sao `zstd` bị loại.
- Thông báo log và ngoại lệ viết bằng tiếng Việt, không dấu ở tên biến/hàm.
- Thêm hàm phức tạp thì thêm test; ưu tiên fixture đại diện trong `tests/fixtures/`,
  đã ẩn danh trước khi đưa vào Git.
- Không hard-code tài khoản, mật khẩu, cookie, CSRF token hay proxy (kể cả trong
  test và tài liệu). Mọi chuỗi proxy đi qua `gdt_tax/proxy.py`; thêm dạng mới thì
  bổ sung test vào `tests/test_proxy.py`.
- Chỉ ghi log ra màn hình; mọi thứ ghi ra file hoặc in ra ở mức `DEBUG` đi qua
  `traffic.py`. Thêm header/trường nhạy cảm mới vào `SENSITIVE_HEADERS` hoặc
  `SENSITIVE_FIELDS` ở đầu module đó.

## Thêm bộ nhận dạng CAPTCHA hoặc nguồn dữ liệu

Hướng dẫn kèm ví dụ nằm ở mục **Mở rộng** trong
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Điểm quan trọng: chỉ cần đăng ký,
không sửa `pipeline.py`.

## Quy ước commit

- Tiêu đề ngắn, tiếng Việt, tập trung vào **lý do** thay vì liệt kê file.
- Một commit nên là một thay đổi mạch lạc, dễ đọc lại.
- Ghi rõ trong phần thân nếu có thay đổi hành vi người dùng sẽ thấy.

Ví dụ:

```text
Chia khoảng tra cứu 31 ngày cho cả DVC và ETAX

Cổng từ chối khoảng dài kể cả trước mốc 01/07/2025, nên chương trình tự cắt
nhỏ và tự chuyển nguồn tại mốc đó.
```

## Quy trình pull request

1. Tạo nhánh từ `main`: `git switch -c fix/ten-ngan`.
2. Chạy test và lint.
3. Mở pull request, mô tả hiện tượng trước — sau, và cách bạn đã kiểm chứng.
4. Nếu thay đổi luồng chạy hoặc module, cập nhật `docs/ARCHITECTURE.md`.

Pull request cần pipeline xanh (job `test`, `lint` và `desktop` trong
`.github/workflows/ci.yml`) trước khi được duyệt.

## Báo lỗi khi cổng đổi giao diện

Đính kèm giúp chúng tôi rất nhiều:

- Lệnh đã chạy và file log đầy đủ:
  ```bash
  python -m gdt_tax --from-date ... --to-date ... --log-file logs/run.log --dump-http http-dump
  ```
  File log ở mức `DEBUG` (kèm header/body của từng request). Bộ che một số
  header/trường có cấu trúc không bảo đảm che bí mật trong URL, Referer và
  HTML/XML response. Không gửi nguyên file; chỉ gửi bản đã kiểm tra và ẩn danh
  tài khoản, mật khẩu, cookie/token/phiên, mã hồ sơ và dữ liệu thuế.
  Xem mục [Chẩn đoán và khắc phục](README.md#chẩn-đoán-và-khắc-phục).
- File `*.response.txt` liên quan trong `http-dump/` — HTML thật của cổng. Nhớ
  **che mã số thuế và mã hồ sơ** của bạn (log không tự che phần này).
- Tên solver CAPTCHA đang dùng (`GDT_CAPTCHA_SOLVER`).
- Có dùng proxy không (`--proxy`/`GDT_PROXY_URL`) và nó có trả về IP Việt Nam
  không (`curl -x … https://ipinfo.io/json`). **Không dán chuỗi proxy kèm tài khoản
  của bạn vào issue.**

Đưa bản HTML đã ẩn danh vào `tests/fixtures/` để người khác tái hiện lỗi.
Không commit `.env`, ZIP/XML tải thật, log/dump thô hoặc token GitHub.
