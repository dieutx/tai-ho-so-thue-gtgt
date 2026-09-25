# Tải hồ sơ thuế GTGT từ Dịch vụ công Thuế

Công cụ Python tự động đăng nhập Cổng Dịch vụ công của Cục Thuế, nhận dạng CAPTCHA bằng EasyOCR, tìm hồ sơ theo khoảng ngày và tải hồ sơ dưới dạng ZIP.

## Chức năng

- Tự chia khoảng tra cứu dài thành các đoạn tối đa 31 ngày.
- Tự chọn nguồn dữ liệu theo ngày:
  - Trước `01/07/2025`: tra cứu Thuế điện tử qua luồng `ETAX`.
  - Từ `01/07/2025`: tra cứu qua luồng Dịch vụ công hiện hành.
- Xử lý đầy đủ phân trang và tải hồ sơ ngay trên từng trang để giữ trạng thái xác thực của máy chủ.
- Nhận dạng CAPTCHA đăng nhập và tìm kiếm bằng EasyOCR.
- Tải đúng endpoint riêng của từng nguồn dữ liệu.
- Giải mã ZIP Base64 và kiểm tra archive trước khi lưu.
- Đặt tên ZIP có mã hồ sơ, kỳ tính thuế, loại tờ khai và tên tờ khai.
- Xuất danh sách chi tiết ra `danh_sach_ho_so.csv` và `danh_sach_ho_so.json`.
- Tự thử lại khi máy chủ trả HTTP 429.
- Bỏ qua ZIP hợp lệ đã tải, thuận tiện khi chạy tiếp sau khi gián đoạn.
- Hỗ trợ tải riêng một mã hồ sơ qua `GDT_CASE_ID`.

## Metadata được xuất

Mỗi hồ sơ có các trường:

- Mã hồ sơ hoặc mã giao dịch
- Nguồn `DVC`/`ETAX`
- Tên thủ tục hành chính
- Tờ khai/phụ lục
- Kỳ tính thuế
- Loại tờ khai
- Lần nộp và lần bổ sung
- Ngày nộp
- Nơi nộp hoặc cơ quan thuế tiếp nhận
- Trạng thái
- Tên file ZIP tương ứng

Ví dụ tên file:

```text
11320250292469209__12-2024__Chinh-thuc__TO-KHAI-THUE-GIA-TRI-GIA-TANG.zip
```

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
$env:GDT_FROM_DATE = "01/01/2025"
$env:GDT_TO_DATE = "31/08/2026"
$env:GDT_DOWNLOAD_DIR = "download"
```

Khoảng ngày có thể dài hơn 31 ngày. Chương trình tự chia nhỏ và tự chuyển giữa ETAX/DVC tại mốc `01/07/2025`.

Không ghi tài khoản, mật khẩu, cookie hoặc CSRF token trực tiếp vào mã nguồn. File `.env.example` chỉ là mẫu và không chứa thông tin thật.

## Chạy chương trình

```powershell
python .\taitokhaiGTGT_fix_v12_full.py
```

Để tải riêng một hồ sơ trong khoảng ngày đã cấu hình:

```powershell
$env:GDT_CASE_ID = "11320250292469209"
python .\taitokhaiGTGT_fix_v12_full.py
```

Xóa bộ lọc để quay lại chế độ tải toàn bộ:

```powershell
Remove-Item Env:GDT_CASE_ID
```

## Cách xử lý phân trang

Cổng Dịch vụ công lưu danh sách hồ sơ của trang tìm kiếm gần nhất trong phiên làm việc. Chương trình thực hiện tuần tự:

1. Tìm một khoảng tối đa 31 ngày.
2. Nạp trang kết quả hiện tại.
3. Tải toàn bộ hồ sơ của trang đó.
4. Chuyển sang trang kế tiếp.
5. Chuyển sang khoảng ngày kế tiếp.

Cách này tránh lỗi `validateIdTkhai` khi thu thập toàn bộ mã hồ sơ trước rồi mới tải.

## Biến môi trường

| Biến | Bắt buộc | Giá trị mặc định | Ý nghĩa |
|---|---:|---|---|
| `GDT_USERNAME` | Có | Không có | Tên đăng nhập DVC Thuế |
| `GDT_PASSWORD` | Có | Không có | Mật khẩu DVC Thuế |
| `GDT_FROM_DATE` | Không | `01/09/2026` | Ngày bắt đầu, định dạng `dd/mm/yyyy` |
| `GDT_TO_DATE` | Không | `25/09/2026` | Ngày kết thúc, định dạng `dd/mm/yyyy` |
| `GDT_DOWNLOAD_DIR` | Không | `download` | Thư mục lưu ZIP và metadata |
| `GDT_CASE_ID` | Không | Trống | Mã hồ sơ cần tải riêng |

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
```

## Lưu ý

Giao diện và endpoint của Cổng Dịch vụ công có thể thay đổi. Hãy sử dụng công cụ với tài khoản và hồ sơ mà bạn có quyền truy cập.
