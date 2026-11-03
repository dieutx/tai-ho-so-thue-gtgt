# Tài khoản cá nhân — ưu tiên Dịch vụ công

Từ bản 2.1.2, tờ khai cá nhân dùng **Dịch vụ công từ mốc chuyển nguồn**
(mặc định 01/07/2025). Kỳ trước dùng **`canhan.gdt.gov.vn/ICanhan`** (DSE).
Không dùng luồng `thuedientu.gdt.gov.vn/etaxnnt` của doanh nghiệp cho cá nhân.
Cookie DVC và cổng cũ được giữ riêng; cùng một lần tra cứu có thể đọc cả hai nguồn.

DVC gửi `doiTuong=CN` tới `/tthc/loginLDAP`; CAPTCHA là 5 ký tự. Desktop thử OCR
tối đa 5 lần rồi chuyển sang nhập tay. Lỗi tài khoản/mật khẩu dừng ngay, không
tự đổi sang cổng cũ hoặc thử thêm mật khẩu. Tài khoản dùng được ở cổng cũ chưa
chắc đăng nhập được DVC; hãy đối chiếu tài khoản trên đúng cổng.

Tắt DVC trong Cài đặt sẽ báo phần kỳ mới chưa đầy đủ. Việc tắt DVC không đổi
mốc ngày và không chuyển hồ sơ kỳ mới sang nguồn cũ.

## Luồng cổng cá nhân cũ đã tích hợp

| Bước | Request đã xác minh | Ghi chú |
|---|---|---|
| Mở phiên | `GET /ICanhan/EstablishSession` | DSE trả JavaScript chuyển tới `/ICanhan/Request?dse_sessionId=...`. |
| Trang đăng nhập | `POST /ICanhan/Request` với `retailIndexProc` / `retailUserLoginProc` | Form `goProcForm`, `dse_nextEventName=start` rồi `ok`. |
| Bước 1 | Form `loginForm`: `_userName`, `capcha` | Mã kiểm tra lấy từ `GET /ICanhan/servlet/ImageServlet`. |
| Bước 2 | Form `loginForm`: `_password` | Chỉ gửi sau khi bước 1 được chấp nhận. |
| Đăng nhập đồng thời | `loginConductForm` + `_loginedConduct=forceLastLogin` | Cổng hỏi “Tài khoản này đang đăng nhập hệ thống”; phải bấm Đồng ý. Không gửi input `type=button` (trình duyệt không gửi khi submit bằng JS); gửi kèm nút làm cổng trả `SystemError`. |
| Trang chủ | `retailHomePageProc` | Lưu `dse_sessionId`, `dse_pageId`, HTML trang chủ để mở nghiệp vụ. |
| Tờ khai | `retailSearchVoucherProc`, form `frm` | `_ngaygui`, `_denngay`, `maGDichArr`, `cboTenTKhai`, `maHdong`; trang sau dùng `GET` + `pn`. |
| Tải tờ khai | `retailSearchVoucherProc` + `dse_nextEventName=download`, form `frmtcuu` | `idTBao=<mã giao dịch>`, `fileFormat=9`, `chkTTS=1`; cổng trả XML `HSoThueDTu`. |
| Thông báo | `retailSearchTaxNoticesProc`, form `frm` | `_ngaygui`, `_denngay`, `maGDichArr`, `idHso`, `cboThongBao`; trang sau dùng `GET` + `pn`. |
| Tải thông báo | `retailSearchTaxNoticesProc` + `dse_nextEventName=download`, form `frmtcuu` | `idTBao`/`loaitbao` lấy từ link `downloadGNT(...)` của từng hàng; cổng trả XML `TBaoThueDTu` hoặc PDF. |

XML tờ khai cá nhân được gói vào ZIP ngay trong bộ nhớ trước khi lưu, để dùng
chung kho ZIP, kiểm tra toàn vẹn và quy ước tên tệp với các nguồn khác. Thông báo
XML được lưu trực tiếp dưới đuôi `.xml`; thông báo PDF vẫn lưu `.pdf`.

## Giới hạn có bằng chứng

| Nhóm | Trạng thái |
|---|---|
| Giấy nộp tiền | HAR có form `TraCuuChungTuProc` nhưng **không có lệnh tải đã xác minh**. Ứng dụng báo `UNSUPPORTED_ACCOUNT_FLOW`, không mượn endpoint doanh nghiệp và không ghi nhận thành công giả. |
| Phân trang | Pager thật ghi `Trang 1 /Tổng số N trang`; trang sau lấy đúng href trong `divPagination` (đủ `dse_pageId`, `dse_processorState`, `pn`). |
| Cổng trả SystemError HTTP 200 | Tự thử lại 3 lần khi tải tệp; nếu vẫn lỗi thì báo “cổng tạm bận”, không lưu HTML thành PDF/XML và không đếm là đã tải. Một số thông báo KDT vẫn có thể lỗi lặp lại do phía cổng. |
| CAPTCHA | `ddddocr` đọc đúng phần lớn ảnh 4–5 ký tự; ảnh mờ có thể bị nhận thiếu ký tự. Desktop có bước nhập tay dự phòng sau khi tự động thất bại. |
| Đổi loại tài khoản | Xoá phiên/cookie và mật khẩu đang giữ, không xoá tệp đã tải. |
| Kho dữ liệu | Cá nhân nằm tại `<Nơi lưu>/ca-nhan/<tài khoản>/...`; kho doanh nghiệp giữ nguyên. |

## Kiểm chứng live

Ngày 03/11/2026, luồng DVC qua `ETaxSessionManager` và pipeline desktop:

- Đăng nhập CN thành công với OCR tự động 5 ký tự.
- Tra cứu 01–31/10/2026: **8 hồ sơ DVC**, không lỗi.
- Tải có chọn lọc 1 hồ sơ: thành công; chạy lại dùng được tệp đã có.
- Tài khoản thử trước đó bị DVC từ chối; đã bổ sung nhận diện thông báo thật
  “Thông tin tài khoản hoặc mật khẩu không đúng” thành `AUTH_INVALID_CREDENTIALS`.

Kiểm chứng cổng cũ từ lượt phát triển trước, chạy trực tiếp `CanhanPortal` qua proxy Việt Nam bằng tài khoản
cá nhân thật (không dùng endpoint doanh nghiệp):

- Đăng nhập hai bước thành công, kể cả bước xác nhận đăng nhập đồng thời; phiên
  có `dse_sessionId` và `dse_pageId`.
- Tờ khai: **4/4 hồ sơ đã tải**, exit 0; ZIP và metadata được kiểm tra toàn vẹn.
- Thông báo: **5/5 tệp đã tải** trên 58 đoạn ngày, exit 0; XML `TBaoThueDTu` hợp lệ.
- Kỳ không có hồ sơ: cổng trả trang tra cứu hợp lệ nhưng không có bảng kết quả;
  CLI ghi nhận `EMPTY_CONFIRMED`, không báo lỗi cấu trúc và không đếm là đã tải.
- CAPTCHA cổng cá nhân dài **4 hoặc 5 ký tự**; `ddddocr` được cấu hình nhận cả
  hai độ dài (doanh nghiệp vẫn chỉ nhận 5).
- Phân trang thông báo: tài khoản có 3 trang/30 bản ghi được đọc đúng số trang và
  href từng trang, không còn lặp lại trang 1.
- Ba tài khoản cá nhân đăng nhập được trong đợt chạy: tờ khai **4/4**, **1/1**,
  **1/1**; thông báo **5/5**, **2/2**; các tài khoản còn lại bị cổng từ chối thông
  tin đăng nhập nên được bỏ qua, không thử mật khẩu lặp lại.

Không có mật khẩu, cookie, token, MST đầy đủ hoặc nội dung hồ sơ nào được ghi
vào mã nguồn, tài liệu hay log bàn giao.

## Cách dùng

1. Chọn **Cá nhân** ở góc trên bên phải; giữ DVC bật trong Cài đặt.
2. Bấm **Đăng nhập**, nhập MST/CCCD/tên đăng nhập cá nhân và mật khẩu DVC.
3. Chọn kỳ, bấm **Tra cứu** hoặc **Tra cứu và tải**.
4. Tab **Thông báo thuế** dùng cổng cá nhân cũ; tab **Giấy nộp tiền** hiện
   thông báo chưa hỗ trợ như bảng trên. Tài khoản cổng cũ cần đăng nhập được ở cổng đó.

CLI dùng cùng định tuyến tờ khai:

```powershell
python -m gdt_tax --account-type CN --enable-dvc --from-date 01/10/2026 --to-date 31/10/2026 --dry-run
python -m gdt_tax.tb --account-type CN --from-date 01/06/2025 --to-date 30/06/2025 --dry-run
```

Credential đọc từ môi trường hoặc `.env` riêng trên máy. Chẩn đoán EXE
`--online-check` nhận thêm `account_type: "CN"`; file yêu cầu không chứa mật khẩu.
