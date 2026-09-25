# Tải hồ sơ thuế GTGT từ Dịch vụ công Thuế

Công cụ Python tự động đăng nhập Cổng Dịch vụ công của Cục Thuế, nhận dạng CAPTCHA bằng EasyOCR, tìm hồ sơ theo khoảng ngày và tải toàn bộ hồ sơ dưới dạng ZIP.

## Chức năng

- Đăng nhập bằng tài khoản doanh nghiệp qua biến môi trường.
- Nhận dạng CAPTCHA đăng nhập và tìm kiếm bằng EasyOCR.
- Đọc đúng tổng số trang và xử lý lần lượt từng trang.
- Tải hồ sơ ngay sau khi nạp từng trang để giữ trạng thái xác thực của máy chủ.
- Giải mã nội dung ZIP được trả về dưới dạng Base64.
- Kiểm tra cấu trúc ZIP trước khi lưu.
- Tự động thử lại khi CAPTCHA sai hoặc máy chủ trả HTTP 429.
- Bỏ qua các ZIP hợp lệ đã tải, thuận tiện khi chạy tiếp sau khi gián đoạn.
- Hỗ trợ tải riêng một mã hồ sơ qua `GDT_CASE_ID`.

## Yêu cầu

- Windows 10/11
- Python 3.10 trở lên
- Kết nối đến `https://dichvucong.gdt.gov.vn`

## Cài đặt

```powershell
git clone https://github.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

EasyOCR sẽ cài PyTorch và tải mô hình nhận dạng trong lần sử dụng đầu tiên.

## Cấu hình

Thiết lập thông tin đăng nhập và khoảng ngày trong PowerShell:

```powershell
$env:GDT_USERNAME = "ma_so_thue-QL"
$env:GDT_PASSWORD = "mat_khau_dich_vu_cong"
$env:GDT_FROM_DATE = "01/09/2026"
$env:GDT_TO_DATE = "25/09/2026"
$env:GDT_DOWNLOAD_DIR = "download"
```

Không ghi tài khoản hoặc mật khẩu trực tiếp vào mã nguồn. File `.env.example` chỉ là mẫu và không chứa thông tin thật.

## Chạy chương trình

```powershell
python .\taitokhaiGTGT_fix_v12_full.py
```

Chương trình tìm tất cả hồ sơ trong khoảng ngày, xử lý từng trang và lưu ZIP vào thư mục `download`.

Để tải riêng một hồ sơ:

```powershell
$env:GDT_CASE_ID = "G12.18-YYMMDD-XXXXXXXX"
python .\taitokhaiGTGT_fix_v12_full.py
```

Xóa biến này để quay lại chế độ tải toàn bộ:

```powershell
Remove-Item Env:GDT_CASE_ID
```

## Cách xử lý phân trang

Cổng Dịch vụ công lưu danh sách hồ sơ của trang tìm kiếm gần nhất trong phiên làm việc. Vì vậy chương trình thực hiện tuần tự:

1. Tìm trang hiện tại.
2. Tải toàn bộ hồ sơ của trang đó.
3. Chuyển sang trang kế tiếp.

Cách này tránh lỗi xác thực `validateIdTkhai` khi thu thập toàn bộ mã hồ sơ trước rồi mới tải.

## Biến môi trường

| Biến | Bắt buộc | Giá trị mặc định | Ý nghĩa |
|---|---:|---|---|
| `GDT_USERNAME` | Có | Không có | Tên đăng nhập DVC Thuế |
| `GDT_PASSWORD` | Có | Không có | Mật khẩu DVC Thuế |
| `GDT_FROM_DATE` | Không | `01/09/2026` | Ngày bắt đầu, định dạng `dd/mm/yyyy` |
| `GDT_TO_DATE` | Không | `25/09/2026` | Ngày kết thúc, định dạng `dd/mm/yyyy` |
| `GDT_DOWNLOAD_DIR` | Không | `download` | Thư mục lưu ZIP |
| `GDT_CASE_ID` | Không | Trống | Mã hồ sơ cần tải riêng |

## Lưu ý

Giao diện và endpoint của Cổng Dịch vụ công có thể thay đổi. Hãy sử dụng công cụ với tài khoản và hồ sơ mà bạn có quyền truy cập.
