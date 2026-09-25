# Đóng góp

Cảm ơn bạn muốn cải thiện công cụ này. Tài liệu ngắn gọn dưới đây giúp bạn chạy
dự án và gửi thay đổi nhanh.

## Chuẩn bị môi trường

```bash
git clone https://github.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
python -m venv .venv
```

Kích hoạt môi trường (Windows: `.\.venv\Scripts\Activate.ps1`, Linux:
`source .venv/bin/activate`) rồi cài:

```bash
pip install -r requirements-dev.txt   # gồm cả easyocr để chạy thử thật
```

Nếu chỉ muốn sửa logic và chạy test, cài tối thiểu là đủ vì test **không** cần `easyocr`:

```bash
pip install beautifulsoup4 lxml requests
```

## Chạy test

```bash
python -m unittest discover -s tests -t . -v
ruff check .
```

Test phải xanh trên cả Windows và Linux trước khi mở pull request — CI cũng chạy
đúng hai hệ điều hành này.

## Nguyên tắc viết mã

- Mỗi module một trách nhiệm. Xem bảng ở [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- Không import `easyocr`/`torch` ở cấp module; chỉ import bên trong hàm để giữ
  cho `import gdt_tax` nhẹ và test chạy không cần OCR.
- Thay đổi giao diện cổng thì sửa `constants.py`, `parsing.py` hoặc portal — không
  rải điều kiện rẽ nhánh khắp nơi.
- Thông báo log và ngoại lệ viết bằng tiếng Việt, không dấu ở tên biến/hàm.
- Thêm hàm phức tạp thì thêm test; ưu tiên fixture HTML thật trong `tests/fixtures/`.
- Không hard-code tài khoản, mật khẩu, cookie hay CSRF token.

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
3. Mở PR, mô tả hiện tượng trước — sau, và cách bạn đã kiểm chứng.
4. Nếu thay đổi luồng chạy hoặc module, cập nhật `docs/ARCHITECTURE.md`.

## Báo lỗi khi cổng đổi giao diện

Đính kèm giúp chúng tôi rất nhiều:

- Lệnh đã chạy và log chạy với `-v`.
- HTML thật của trang kết quả **đã che** mã số thuế và mã hồ sơ của bạn.
- Tên solver CAPTCHA đang dùng (`GDT_CAPTCHA_SOLVER`).

Dán HTML vào `tests/fixtures/` là cách nhanh nhất để người khác tái hiện lỗi.
