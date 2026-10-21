# Rà soát lỗi bảng và phân trang — 22/10/2026

Phạm vi: parser tờ khai DVC/ETAX/ETAX_LEGACY, GNT, TB, thông báo đính kèm
legacy/DVC, nhận diện rỗng/CAPTCHA và bộ điều khiển phân trang dùng các parser
này. Đây là review nhóm lỗi cấu trúc HTML và định danh hàng; không phải chứng
nhận toàn bộ chương trình hoặc mọi biến thể cổng trong tương lai không có lỗi.

## Lỗi trên cổng thật

1. **DVC:** tiêu đề `Lần nộp (Tờ khai)/File số (DLVC)` chưa có alias, gây đúng
   `REQUIRED_COLUMNS_MISSING_OR_AMBIGUOUS:lan_nop` người dùng báo. Sau khi nhận
   tên cột còn lộ `ROW_SCHEMA_MISMATCH`: 13 tiêu đề nhưng chỉ 12 ô dữ liệu.
   Bổ sung alias riêng DVC; chỉ chấp nhận thiếu ô tùy chọn cuối hàng.
2. **ETAX:** hai div cùng lớp `bangKetQuaTraCuu_tdt`; div đầu không có bảng,
   div sau có đủ 11 cột và hai hàng hợp lệ. `select_one` bỏ sót bảng và báo
   `RESULT_TABLE_MISSING_OR_AMBIGUOUS`. Nay duyệt mọi scope, gộp cùng một bảng
   theo danh tính DOM; nhiều bảng thực sự khác nhau vẫn bị báo mơ hồ.

Kiểm thử source có quyền, chỉ tra cứu trong thư mục cache riêng:

| Adapter | Khoảng | Hồ sơ | Kết quả |
| --- | --- | ---: | --- |
| DVC | 09/2026 | 24 | SUCCESS sau sửa |
| DVC | 01–22/10/2026 | 10 | SUCCESS sau sửa |
| ETAX | 06/2025 | 2 | SUCCESS sau sửa |
| ETAX_LEGACY | 06/2025 | 2 | SUCCESS |
| GNT | 09/2026 | 12 | SUCCESS, hai trang |
| TB | 09/2026 | 7 | SUCCESS |

Các lượt này không chứng minh tải tệp. Bằng chứng EXE/tải/reuse phải kiểm tra
riêng, đối chiếu SHA mã nguồn và checksum artifact trong receipt bàn giao.

## Lỗi bổ sung tái hiện bằng dữ liệu tổng hợp

- **Thông báo legacy phụ thuộc vị trí/cách viết th/td:** đảo cột có tên đầy đủ
  hoặc đổi th thành td trong thead bị `SCHEMA_UNKNOWN`. Dùng chung bộ ánh xạ
  header có tên; vẫn từ chối cột trùng/thiếu hoặc ô dữ liệu gộp bất thường.
- **Thông báo/rỗng bị ảnh hưởng HTML ẩn:** placeholder “Không có dữ liệu” có
  thể làm trang lạ thành rỗng hợp lệ; placeholder “Không có thông báo” có thể
  xung đột với thông báo thật. Đọc text hiện hữu bằng helper không sửa DOM;
  nội dung modal Bootstrap vẫn được đọc khi chính modal chưa mở.
- **Phân trang GNT/TB:** chuỗi `Trang 1/999` trong div ẩn trước bộ đếm thật
  có thể ghi đè số trang. Loại text ẩn trước khi đọc bộ đếm.
- **CAPTCHA hiện đại:** phản hồi có table bố cục, JSON code hoặc câu
  “Mã xác thực không chính xác” có thể bị báo lỗi schema. Chỉ khi không có
  hồ sơ và kết quả chưa đầy đủ, dùng classifier xác thực chung để phản hồi
  `CAPTCHA_INVALID` và thử lại hữu hạn; text ẩn không tính là bị từ chối.
- **GNT có ID handler xung đột:** `chiTietCT(A)` và `downloadGNT(B)` trước
  đây chọn ID đầu trong HTML. Nay từ chối hàng có hai ID khác nhau, giữ hàng
  hợp lệ khác để không gán nhầm định danh tệp.
- **Scope bản thân là table/nhiều scope:** table mang class/id kết quả bị bỏ
  vì chỉ tìm hậu duệ; nhiều bảng khác nhau bị bỏ qua khi chỉ dùng scope đầu.
  Bộ tìm bảng xử lý chính table, scope lồng nhau và phân biệt mơ hồ thực sự.

12 phương thức test mới phủ các trường hợp trên và cách xuống dòng/viết header
ở cả năm adapter. Chạy cùng test trên snapshot commit trước review `5246b47`:
11 phương thức thất bại; sau bản sửa cả 12 đạt. Không coi các biến thể tổng
hợp là lỗi đã quan sát trên cổng thật. Smoke source/frozen có DVC 12 ô, ETAX
nhiều scope, thông báo legacy đảo cột, text ẩn, CAPTCHA có table và phân trang.

## Lỗi đóng gói bắt được trước bàn giao

`scripts/write_release_metadata.py` import `desktop` theo môi trường Python.
Khi chạy script bằng đường dẫn từ checkout cô lập nhưng interpreter có editable
install ở checkout cũ, metadata/Windows resource ghi 2.0.0 trong khi ứng dụng
và smoke chạy 2.0.4. Receipt trước đây chỉ so source SHA, nên chưa chặn lệch
phiên bản; bước bàn giao riêng đã chặn artifact này trước khi đưa vào `dist`
chính hoặc chạy online EXE.

Nay đọc literal phiên bản bằng AST trực tiếp từ file mã nguồn đúng checkout;
không import package từ môi trường đã cài. Test mô phỏng package cũ trong
`sys.modules` và source khác để xác minh metadata/Windows version đúng nguồn.
Build so phiên bản trước PyInstaller; smoke so phiên bản code với metadata
thật trong bundle; receipt bắt buộc source/frozen/version/core version khớp.

## Giới hạn được giữ

- Không thêm alias theo suy đoán hoặc nới cột bắt buộc cho mọi nguồn.
- Thiếu cột giữa, số lần nộp sai, handler đổi, nhiều bảng hoặc cột trùng vẫn
  báo chưa đầy đủ; không coi trang không hiểu là không có hồ sơ.
- Phân trang thông báo đính kèm legacy nhiều trang vẫn được báo chưa đầy đủ
  theo policy đã có; không tự đoán luồng duyệt hoặc bỏ thông báo.
- Không sửa thư mục hồ sơ người dùng, sao chép credential vào Git/fixture,
  hoặc publish/tag/replace release công khai trong lượt này.
