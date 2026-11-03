# Tài khoản cá nhân — luồng Thuế điện tử cá nhân (đã xác minh từ HAR)

Tài khoản cá nhân dùng **`canhan.gdt.gov.vn/ICanhan`** (DSE), tách hẳn khỏi
`dichvucong.gdt.gov.vn` và `thuedientu.gdt.gov.vn/etaxnnt` của doanh nghiệp.
Tài liệu này chỉ ghi endpoint/tham số đã thấy trong HAR; không có cookie, token,
mật khẩu, MST hay nội dung hồ sơ thật trong mã nguồn.

## Luồng đã tích hợp

| Bước | Request đã xác minh | Ghi chú |
|---|---|---|
| Mở phiên | `GET /ICanhan/EstablishSession` | DSE trả JavaScript chuyển tới `/ICanhan/Request?dse_sessionId=...`. |
| Trang đăng nhập | `POST /ICanhan/Request` với `retailIndexProc` / `retailUserLoginProc` | Form `goProcForm`, `dse_nextEventName=start` rồi `ok`. |
| Bước 1 | Form `loginForm`: `_userName`, `capcha` | Mã kiểm tra lấy từ `GET /ICanhan/servlet/ImageServlet`. |
| Bước 2 | Form `loginForm`: `_password` | Chỉ gửi sau khi bước 1 được chấp nhận. |
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
| Đổi loại tài khoản | Xoá phiên/cookie và mật khẩu đang giữ, không xoá tệp đã tải. |
| Kho dữ liệu | Cá nhân nằm tại `<Nơi lưu>/ca-nhan/<tài khoản>/...`; kho doanh nghiệp giữ nguyên. |

## Kiểm chứng live

Ngày 03/11/2026, chạy trực tiếp `CanhanPortal` qua proxy Việt Nam bằng tài khoản
cá nhân thật (không dùng endpoint doanh nghiệp):

- Đăng nhập hai bước thành công; phiên có `dse_sessionId` và `dse_pageId`.
- Tra cứu tờ khai: HTTP 200, **10 hồ sơ**; tải thử hồ sơ đầu tiên được ZIP
  **2.342 bytes**, `validate_tax_zip` hợp lệ.
- Tra cứu thông báo: HTTP 200, **10 thông báo**; tải thử thông báo đầu tiên được
  XML **7.801 bytes**, `validate_xml(..., "notice")` hợp lệ.
- CAPTCHA của cổng cá nhân là ảnh 5 ký tự; bộ đọc tự động `ddddocr` đọc sai
  trong lần chạy này, nên lần kiểm chứng dùng nhập tay. Desktop vẫn có bước nhập
  tay dự phòng sau khi tự động thất bại.

Không có mật khẩu, cookie, token, MST đầy đủ hoặc nội dung hồ sơ nào được ghi
vào mã nguồn, tài liệu hay log bàn giao.

## Cách dùng

1. Chọn **Cá nhân** ở góc trên bên phải.
2. Bấm **Đăng nhập**, nhập MST/tên đăng nhập cá nhân và mật khẩu.
3. Chọn kỳ, bấm **Tra cứu** hoặc **Tra cứu và tải**.
4. Tab **Thông báo thuế** dùng cùng phiên cá nhân; tab **Giấy nộp tiền** hiện
   thông báo chưa hỗ trợ như bảng trên.
