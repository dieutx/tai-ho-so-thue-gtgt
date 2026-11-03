# Tài khoản cá nhân — luồng đã xác minh từ HAR

Tài liệu này ghi lại các endpoint đã quan sát trong HAR tài khoản cá nhân
(`dichvucong.gdt.gov.vn` + `canhan.gdt.gov.vn`). Không có cookie, token, mật
khẩu, MST hay nội dung hồ sơ nào được sao chép vào mã nguồn hoặc tài liệu.

## Đã tích hợp

| Bước | Request đã xác minh | Ghi chú |
|---|---|---|
| Đăng nhập | `GET /tthc/login`, `POST /tthc/loginLDAP` | Form gồm `tenDN`, `matKhau` (Base64), `doiTuong`, `captcha`; cá nhân dùng `doiTuong=CN`, doanh nghiệp dùng `DN`. Phản hồi JSON `{"status":"200"}`. |
| Trang chủ | `GET /tthc/home` | Hiển thị MST/tên người nộp thuế của phiên. |
| Tra cứu tờ khai | `GET /tthc/ho-so/search` | Tham số `maNghiepVu`, `maTTHC`, `maToKhai`, `maHoSo`, `tuNgay`, `denNgay`, `scope_tdt1=SELF`, `mstUyQuyen_tdt1`, `captcha`, `page`, `size`; trả HTML bảng kết quả. |
| Chi tiết hồ sơ | `GET /tthc/tchs/files/detail/{maHoSo}?loai=` | Lấy CSRF của form tải. |
| Kiểm tra tải | `GET /tthc/tchs/validateIdTkhai?idTKhai=` | Trả `200` khi endpoint AJAX còn hỗ trợ. |
| Tải hồ sơ | `POST /tthc/tchs/downloadhoso` | JSON `{"maHoSo": ...}` → `fileName`, `fileType`, `content` (Base64). |
| Tải thông báo đính kèm | `POST /tthc/tchs/downloadthongbao` | JSON `{"idTbao": ..., "loaiTBao": ...}` → cùng cấu trúc. |

Vì vậy chế độ cá nhân dùng lại `DvcPortal` với phiên DVC riêng, không dùng
endpoint legacy `thuedientu.gdt.gov.vn` của doanh nghiệp.

## Chưa tích hợp (cần làm tiếp)

| Nhóm | Luồng quan sát trong HAR | Trạng thái |
|---|---|---|
| Giấy nộp tiền | `GET /tthc/tracuu-chungtu/init`, `GET /tthc/tracuu-chungtu/tracuu`, `GET /tthc/tracuu-chungtu/inchungtu?idChungTu=` | Chưa có parser/lưu trữ tương ứng; ứng dụng báo `UNSUPPORTED_ACCOUNT_FLOW`, không giả kết quả. |
| Thông báo thuế (SSO) | `GET canhan.gdt.gov.vn/ICanhan/` → `EstablishSession` → `retailUserLoginProc` → `retailIndexProc` → `retailSearchTaxNoticesProc`; form `frm`/`frmtcuu`; tải bằng `idTBao`, `loaitbao`, `dse_nextEventName=download` | Chưa tích hợp. Đây là phiên DSE riêng, không dùng chung endpoint doanh nghiệp. |

## 04/SS-HĐĐT và hồ sơ “Chưa tải”

HAR thao tác ngày 16/10/2026 xác nhận cổng trả bảng hồ sơ và cả
`downloadhoso` lẫn `downloadthongbao` đều thành công cho các hồ sơ
`04/SS-HDDT` cùng ngày. Vì vậy không được kết luận “cổng không có tệp” chỉ từ
ảnh. Với hai hồ sơ cụ thể còn thiếu, cần đối chiếu mã hồ sơ trong catalog và
phản hồi tải tương ứng; thống kê chỉ được cập nhật khi tệp thực sự hợp lệ.

## Cách dùng

1. Chọn **Cá nhân** ở góc trên bên phải.
2. Bấm **Đăng nhập**, nhập đúng tài khoản/MST cá nhân và mật khẩu.
3. Chọn kỳ, bấm **Tra cứu** hoặc **Tra cứu và tải**.
4. Kho cá nhân nằm tách biệt tại `<Nơi lưu>/ca-nhan/<tài khoản>/...`; kho doanh
   nghiệp cũ không bị di chuyển hay ghi đè.

Đổi loại tài khoản sẽ đăng xuất phiên hiện tại và xoá dữ liệu đang hiển thị
trên màn hình, nhưng không xoá tệp đã tải.
