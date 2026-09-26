# Đóng góp

Cảm ơn bạn muốn cải thiện công cụ này. Tài liệu ngắn gọn dưới đây giúp bạn chạy
dự án và gửi thay đổi nhanh.

## Chuẩn bị môi trường

```bash
git clone https://gitlab.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
python -m venv .venv
```

Kích hoạt môi trường (Windows: `.\.venv\Scripts\Activate.ps1`, Linux:
`source .venv/bin/activate`) rồi cài:

```bash
pip install -r requirements-dev.txt   # requirements.txt (gồm ddddocr) + ruff + mypy
```

Nếu chỉ muốn sửa logic và chạy test, cài tối thiểu là đủ vì test **không** cần `easyocr`:

```bash
pip install beautifulsoup4 lxml requests
```

## Chạy test

```bash
python -m unittest discover -s tests -t . -v
ruff check .
mypy gdt_tax
```

Test phải xanh trước khi mở merge request — CI trên GitLab chạy đúng các lệnh ở
trên trên Linux; nếu bạn sửa code liên quan tới Windows thì chạy thử thêm trên
Windows trước khi mở MR.

## Chuẩn cho một bộ nhận dạng CAPTCHA mới

Trước khi đề xuất đổi mặc định, hãy đo và ghi lại số liệu theo đúng quy trình ở
mục **Benchmark** trong README (đăng nhập một lần, sau đó N lần "lấy CAPTCHA mới
→ đọc → gửi lên cổng", đếm số lần cổng trả `status = 200`). Cỡ mẫu nên từ 20 lần
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
- Thêm hàm phức tạp thì thêm test; ưu tiên fixture HTML thật trong `tests/fixtures/`.
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

## Quy trình merge request

1. Tạo nhánh từ `main`: `git switch -c fix/ten-ngan`.
2. Chạy test và lint.
3. Mở merge request, mô tả hiện tượng trước — sau, và cách bạn đã kiểm chứng.
4. Nếu thay đổi luồng chạy hoặc module, cập nhật `docs/ARCHITECTURE.md`.

Merge request cần pipeline xanh (job `test` và `lint` trong `.gitlab-ci.yml`)
trước khi được duyệt.

## Báo lỗi khi cổng đổi giao diện

Đính kèm giúp chúng tôi rất nhiều:

- Lệnh đã chạy và file log đầy đủ:
  ```bash
  python -m gdt_tax --from-date ... --to-date ... --log-file logs/run.log --dump-http http-dump
  ```
  File log luôn ở mức `DEBUG` (kèm header/body của từng request); `Cookie`,
  `Set-Cookie`, `Authorization`, `matKhau`, `_csrf` đã bị che thành `***` trước khi
  ghi, nên gửi kèm được. Xem mục **Ghi log và lưu lại traffic** trong README.
- File `*.response.txt` liên quan trong `http-dump/` — HTML thật của cổng. Nhớ
  **che mã số thuế và mã hồ sơ** của bạn (log không tự che phần này).
- Tên solver CAPTCHA đang dùng (`GDT_CAPTCHA_SOLVER`).
- Có dùng proxy không (`--proxy`/`GDT_PROXY_URL`) và nó có trả về IP Việt Nam
  không (`curl -x … https://ipinfo.io/json`). **Không dán chuỗi proxy kèm tài khoản
  của bạn vào issue.**

Dán HTML vào `tests/fixtures/` là cách nhanh nhất để người khác tái hiện lỗi.
