# ĐẶC TẢ UX/UI — TẢI HỒ SƠ THUẾ 2.0

**Mục đích:** Tài liệu bàn giao thiết kế cho nhóm phát triển ứng dụng Windows.
**Đối tượng chính:** Kế toán doanh nghiệp, nhân viên nội bộ xử lý hồ sơ eTax.
**Phạm vi:** Nâng cấp giao diện và trải nghiệm, giữ toàn bộ nghiệp vụ của phiên bản 1.1.0. Không mặc định thay đổi bộ máy tra cứu/tải phía sau.
**Kèm theo:** `tai_ho_so_thue_v2_prototype.html` — nguyên mẫu tương tác chạy độc lập, dữ liệu giả lập.

## 1. Định hướng sản phẩm

**Tuyên ngôn thiết kế:** *Mở ứng dụng → chọn kỳ → tra cứu → kiểm tra tình trạng → tải → đối soát kết quả.*

1. Thể hiện tình trạng hồ sơ **theo cơ quan thuế** và tình trạng **lưu tệp cục bộ** bằng hai trường tách biệt.
2. Giảm số lần cần mở nhật ký kỹ thuật để hiểu vì sao thao tác thất bại.
3. Giữ bảng dữ liệu làm trung tâm; tránh dashboard với quá nhiều biểu đồ và thẻ.
4. Mỗi thao tác quan trọng có kết quả xác nhận; không đánh đồng "có kết nối" với "truy vấn thành công".
5. Không xóa hoặc làm mất dữ liệu đã tải khi người dùng nhấn Dừng/Thử lại/Đổi tài khoản.

### Tiêu chí thành công đề xuất (kiểm thử thực tế)
- Người dùng mới xác định được cách tra cứu và tải trong vòng 1 phút, không cần hướng dẫn.
- Tìm và mở hồ sơ cụ thể trong tối đa 3 thao tác sau khi có danh sách.
- Khi tác vụ thất bại, người dùng nêu được nguyên nhân và bước xử lý từ giao diện, không bắt buộc mở log.
- Người dùng phân biệt được trạng thái "Đã chấp nhận" và "Đã tải tệp".
- Cửa sổ 1080 × 700 px vẫn có bảng nhìn được, không che thao tác chính.

## 2. Sơ đồ thông tin

**Thanh tiêu đề:** Tải Hồ Sơ Thuế · phiên bản · tên doanh nghiệp/MST · kết nối eTax · Lịch sử · Cài đặt · Đổi tài khoản.

**Bốn tab ngang:**
- **Tờ khai** — tra cứu, lọc, tải ZIP, trạng thái tiếp nhận, kỳ tính thuế.
- **Giấy nộp tiền** — tra cứu, lọc, tải XML, mã GNT, số tiền, trạng thái phê duyệt/nộp.
- **Thông báo thuế** — tra cứu, lọc, tải PDF, số thông báo, thời điểm gửi, trạng thái xem.
- **Phân tích XML** — chọn/kéo thả tệp, cấu trúc, các trường nghiệp vụ trích xuất, thông báo lỗi định dạng; cần xây dựng parser nghiệp vụ riêng.

**Tác vụ khác:** Báo cáo tải · Lịch sử tải · Mở thư mục · Tải các nhóm liên tiếp · Đọc/sao chép dữ liệu cũ · Tệp đã tạo · Nhật ký kỹ thuật.

Thao tác dùng nhiều cần hiển thị sẵn; chức năng hiếm dùng gom trong **Công cụ nâng cao**, không xóa.

## 3. Cấu trúc màn hình chính

### 3.1. Thanh đầu ứng dụng
- Cao khoảng 56–68 px, tự giảm ở cửa sổ thấp.
- Bên trái logo chữ giản dị + “Tải Hồ Sơ Thuế 2.0”.
- Bên phải trạng thái "eTax đã kết nối / cần đăng nhập lại / mất kết nối / đang kiểm tra".
- Khối tài khoản hiển thị tên đơn vị và MST; thay thế viết tắt khó hiểu "Đổi TK".
- Trạng thái kết nối **không** được tự đổi sang "tra cứu thành công".

### 3.2. Tab
- Tab được chọn có gạch chân màu xanh; có tổng số hồ sơ theo nhóm.
- Không dùng thêm sidebar nếu chỉ có bốn mục chính.
- Khi đổi tab: **giữ bộ lọc ngày, nơi lưu và phiên đăng nhập**; khởi tạo lại ô tìm kiếm/bộ lọc hàng và vùng chọn để tránh tải nhầm dữ liệu giữa tab.
- Nếu đang tải, yêu cầu xác định chính sách: cho phép đổi tab và tác vụ chạy tiếp, đồng thời giữ tiến trình ở khu vực luôn thấy.

### 3.3. Tra cứu
- Nhãn thời gian biến đổi theo nhóm: Tờ khai = **ngày nộp**, GNT = **ngày lập**, Thông báo = **ngày gửi**.
- Hai ngày theo `dd/MM/yyyy` nhưng xử lý và sắp xếp bằng đối tượng `datetime`/timestamp; lưu dạng ISO 8601.
- Preset: Tháng này, Quý này, Năm nay, 12 tháng qua; có ngày tùy chỉnh.
- Lỗi nhập: thiếu ngày, Từ ngày > Đến ngày, ngoài khoảng eTax hỗ trợ, yêu cầu quá rộng.
- Hai hành động riêng **Tra cứu** (không tải), **Tra cứu và tải** (tra cứu rồi tải theo chính sách bỏ trùng).
- Sau tra cứu thành công, **thu gọn điều kiện** thành một thanh tóm tắt có nút “Sửa điều kiện” để trả thêm không gian cho bảng.
- Đường dẫn lưu dùng tên thư mục dễ đọc, có **Thay đổi** và **Mở thư mục**; chi tiết đường dẫn đầy đủ trong tooltip/cài đặt.

### 3.4. Tổng quan và thông báo
- Tối đa bốn chỉ số: **Tìm thấy · Đã tải · Chưa tải · Tải lỗi**.
- Chỉ tính theo cùng khoảng thời gian và tab đang mở; chú thích rõ bộ lọc bảng có ảnh hưởng chỉ số hay không. Đề xuất chỉ số áp dụng theo thời gian, **không** theo từ khóa tìm kiếm, để tránh nhảy số bất ngờ.
- Thông báo tiến trình phải có mã tác vụ, tổng số, đã tải, lỗi, bỏ qua, chưa xử lý; lý do bỏ qua phải tra được.
- Thành công bình thường: thông báo nhẹ hoặc tự ẩn. Lỗi: có hành động **Xem chi tiết** hoặc **Thử lại tệp lỗi**.

### 3.5. Bảng và tương tác chung
- Sticky header khi nhiều dòng, cuộn dữ liệu trong khung; dùng virtualized table nếu rất nhiều dòng.
- Header cột cho phép sắp xếp tăng/giảm. Mặc định ngày mới nhất trước; sắp xếp theo timestamp, không theo chuỗi `dd/MM/yyyy`.
- Độ rộng phân bổ ưu tiên **tên hồ sơ**, **ngày**, **trạng thái**; dòng mã rất dài cần ellipsis + tooltip và nút sao chép ở bảng chi tiết.
- Checkbox đầu dòng và checkbox trên header để chọn nhiều; xác định rõ "chọn trên trang" hay "chọn mọi kết quả".
- Nhấp dòng mở chi tiết bên phải; Enter xem chi tiết; Ctrl+F tập trung ô tìm kiếm; Escape đóng dialog.
- Tìm kiếm theo tên, mã, kỳ; bộ lọc chung: tất cả, chưa tải, đã tải, tải lỗi, cần kiểm tra.
- Nút **Tải chưa tải** ở phần danh sách; sau khi chọn nhiều dòng xuất hiện **Tải các tệp đã chọn** và **Bỏ chọn**.
- Bảng dùng phân trang 25/50/100 hoặc cuộn ảo trong sản phẩm thật. Mẫu minh họa dùng 10 dòng mỗi trang để dễ thử.

## 4. Chi tiết từng nhóm nghiệp vụ

### 4.1. Tờ khai
**Cột:** Chọn · Hồ sơ (mã + tên) · Kỳ tính thuế · Ngày nộp · Trạng thái thuế · Tệp trên máy · Hành động.

**Trạng thái thuế:** Đã chấp nhận / Không chấp nhận / Đang xử lý / Trạng thái khác trả về từ eTax. Không suy diễn các trạng thái chưa nhận được.

**Trạng thái tệp:** Chưa tải / Đang tải / Đã tải / Tải lỗi / Bỏ qua (xem lý do). Trạng thái thuế "Không chấp nhận" **không tự động loại hồ sơ khỏi danh sách tải**, tùy chính sách nghiệp vụ.

**Chi tiết hồ sơ:** Mã tờ khai, tên đầy đủ, kỳ tính thuế, ngày nộp, mã tiếp nhận (nếu có), trạng thái, đường dẫn ZIP, thông tin lỗi/tải, thao tác tải/mở/sao chép.

### 4.2. Giấy nộp tiền
**Cột:** Chọn · Số GNT (rút gọn) · Ngày lập · Số tiền · Trạng thái nộp/phê duyệt · Tệp trên máy · Hành động.

- Số tiền căn phải và định dạng theo locale `vi-VN`, có ký hiệu `₫`.
- Số GNT dài: không hiển thị toàn bộ trong bảng, cung cấp copy trong chi tiết.
- Nhóm **Cần kiểm tra** chứa chứng từ bị từ chối phê duyệt hay trạng thái nghiệp vụ bất thường, tách khỏi nhóm **Tải lỗi**.
- Tránh hiển thị tổng tiền như nghĩa vụ thuế đã thanh toán nếu chưa có quy tắc loại trùng/chứng từ bị từ chối; nếu cung cấp tổng, cần ghi rõ tiêu chí tính.

### 4.3. Thông báo thuế
**Cột:** Chọn · Tên và số thông báo · Ngày gửi · Trạng thái xem · Tệp PDF · Hành động.

- Đã xem là trạng thái thông báo, không có nghĩa PDF đã lưu.
- Mỗi lỗi tải phải gắn với bản ghi hoặc ít nhất gắn với mã tác vụ và nguồn lỗi; không hiện "Lỗi 1" chung chung.
- Có thể xem trước PDF nếu ứng dụng Windows có công cụ xem nội bộ phù hợp; mở bằng ứng dụng mặc định là phương án nhẹ nhất.

### 4.4. Phân tích XML
- Khu vực chọn tệp hoặc kéo/thả, tệp được phân tích cục bộ.
- Phân tích cú pháp XML, sau đó bộ nhận dạng phiên bản mẫu tờ khai, kỳ, số thuế, MST, chỉ tiêu khi biết schema.
- Báo lỗi cấu trúc rõ; không được tuyên bố "hợp lệ về nghiệp vụ/chữ ký số" chỉ dựa vào XML parse thành công.
- Chức năng đề xuất: danh sách chỉ tiêu, so sánh hai tệp, xuất CSV/Excel về sau; không mặc định đưa vào phạm vi tối thiểu.

## 5. Luồng xử lý

### A. Tra cứu đơn thuần
Chọn tab → Chọn khoảng ngày → Tra cứu → Hiển thị số kết quả → Thu gọn bộ lọc → Người dùng tìm/lọc/xem chi tiết hoặc tải.

### B. Tra cứu và tải
Chọn khoảng ngày + nơi lưu → Tra cứu và tải → Nhận danh sách → Đối chiếu tệp hiện có → Lập hàng đợi → Hiển thị tiến trình → Kết thúc với tổng kết tải, bỏ qua, lỗi → Mở lịch sử nếu cần.

### C. Tải lỗi
Tệp chuyển sang **Tải lỗi** → Ghi `error_code`, `message_for_user`, `technical_message`, `retryable`, `task_id`, thời gian → Hiển thị nguyên nhân và bước xử lý → **Thử lại** đúng những tệp có thể thử lại. Ví dụ: hết phiên đăng nhập phải có nút Đăng nhập lại trước khi tải.

### D. Dừng tác vụ
Dừng nhận thêm tác vụ, không xóa những tệp đã lưu thành công; tệp chưa hoàn tất phải được xử lý bằng ghi tệp tạm + đổi tên nguyên tử (atomic rename), tránh tệp ZIP/PDF/XML hỏng nhưng vẫn hiển thị "Đã tải".

### E. Tải trùng
Nhận diện tệp bằng tổ hợp tài khoản, loại hồ sơ, mã hồ sơ, phiên bản/ngày phát hành và/hoặc hash; xác minh kích thước/nội dung khi có thể. Không chỉ so sánh tên tệp. Nếu khác nội dung thì lưu phiên bản mới hoặc yêu cầu người dùng quyết định.

## 6. Mô hình dữ liệu trạng thái tối thiểu

```text
DocumentRecord
  account_id             // tài khoản eTax được sử dụng
  document_type          // return | payment | notification
  document_id            // mã hồ sơ/giấy nộp tiền/thông báo
  title, tax_period
  event_datetime         // ISO 8601
  business_status        // giá trị từ eTax, độc lập file_status
  business_status_raw    // giá trị gốc để đối chiếu
  amount, currency       // chỉ dùng cho GNT
  file_status            // not_downloaded | queued | downloading |
                         // downloaded | failed | skipped
  file_name, file_path
  file_format            // ZIP | XML | PDF
  file_size, file_hash
  last_downloaded_at
  error_code, error_message, error_detail
  last_task_id

Task
  task_id, account_id, document_type, date_from, date_to
  mode                   // query | query_and_download | download_selected
  status                 // queued | running | paused | cancelled | finished
  found, downloaded, failed, skipped, pending
  started_at, ended_at
```

**Quan trọng:** "bỏ qua" là kết quả tác vụ, có thể do tệp đã tồn tại. Không được luôn gộp "bỏ qua" vào "đã tải" nếu chưa xác minh file.

## 7. Trạng thái giao diện và câu chữ

| Tình huống | Nội dung chính | Hành động |
|---|---|---|
| Chưa đăng nhập eTax | Cần đăng nhập eTax để tra cứu | Đăng nhập |
| Đã kết nối | eTax đã kết nối | Không yêu cầu hành động |
| Đang tra cứu | Đang tra cứu hồ sơ… | Dừng (nếu hỗ trợ) |
| Không có dữ liệu | Không tìm thấy hồ sơ trong khoảng ngày này | Đổi khoảng ngày |
| Tra cứu thành công | Tìm thấy 15 hồ sơ | Xem danh sách |
| Đang tải | Đang tải 8/15 tệp | Dừng |
| Tải xong một phần | Đã tải 12, lỗi 2, bỏ qua 1 | Xem lỗi / Thử lại |
| Kết nối hết hạn | Phiên eTax đã hết hạn | Đăng nhập lại |
| Không có quyền lưu | Không thể ghi tệp vào thư mục đã chọn | Đổi thư mục |
| Hồ sơ bị từ chối | Không chấp nhận / Bị từ chối phê duyệt | Xem trạng thái nghiệp vụ |

Tránh “Chỉ tra cứu” trong cột trạng thái tệp; đó là **chế độ tác vụ**, không phải trạng thái của tệp.

## 8. Bộ quy tắc thiết kế

| Thuộc tính | Giá trị định hướng |
|---|---|
| Font | Segoe UI (Windows), fallback hệ thống |
| Body | 12–13 px ở desktop, hiển thị rõ tiếng Việt |
| Tiêu đề màn hình | 18–22 px / weight 700 |
| Nền | `#F5F7FB` |
| Thẻ/bảng | `#FFFFFF` |
| Chữ chính | `#17263D` |
| Chữ phụ | `#67768C` |
| Đường viền | `#E4EAF2` |
| Màu hành động chính | `#225DE9` |
| Thành công | `#15805B` |
| Cảnh báo | `#93631B` |
| Lỗi | `#C94242` |
| Bo góc | 8–12 px |
| Chiều cao nút | 32 px chế độ gọn / 37 px bình thường |
| Chiều cao dòng bảng | 43 px chế độ gọn / 53 px bình thường |
| Kích thước mục tiêu | 1080 × 700, 1366 × 768; kiểm tra ở 125%/150% scale Windows |

Không chỉ dùng màu để biểu thị trạng thái: thêm chữ và biểu tượng tương ứng; kiểm thử contrast WCAG AA. Người dùng thao tác nhiều bằng bàn phím phải dùng được mà không cần chuột.

## 9. Danh mục chức năng cũ → vị trí mới

| Chức năng v1.1.0 | Vị trí v2.0 | Lưu ý |
|---|---|---|
| Tờ khai | Tab Tờ khai | ZIP |
| Giấy nộp tiền | Tab Giấy nộp tiền | XML, số tiền |
| Thông báo thuế | Tab Thông báo thuế | PDF |
| Phân tích XML | Tab Phân tích XML | Không bỏ |
| Chọn Từ/Đến | Thanh điều kiện | Preset + tùy chỉnh |
| Lưu / Thư mục | Dòng thư mục + Cài đặt | Có nút mở |
| Tra cứu | Nút Tra cứu | Không tải |
| Tra cứu, tải | Nút Tra cứu và tải | Chống trùng |
| Dừng | Trên bảng tiến trình | Không xóa dữ liệu đã lưu |
| Đổi TK | Khối tài khoản ở tiêu đề | Chuyển MST an toàn |
| Tệp nhật ký | Lịch sử tải + Nhật ký kỹ thuật | Phân vai trò |
| Mở báo cáo | Báo cáo tải | Lọc/xuất |
| Nhật ký (144) | Lịch sử / Nhật ký kỹ thuật | Hiển thị số sự kiện theo thực tế |
| Tải các nhóm liên tiếp | Công cụ nâng cao | Tiến trình riêng |
| Đọc / sao chép dữ liệu cũ | Công cụ nâng cao | Có xem trước và chống ghi đè |
| Tệp đã tạo | Công cụ nâng cao | Tải/mở từng tệp |

## 10. Rủi ro và bảo vệ dữ liệu

- MST, số GNT, đường dẫn hệ thống, nội dung XML, thông tin phiên đăng nhập là dữ liệu có thể nhạy cảm; **mã hóa / che một phần trong log chia sẻ**, không in token/cookie/chữ ký số vào log.
- Không lưu mật khẩu hoặc cookie eTax dưới dạng plaintext, cân nhắc Windows Credential Manager / DPAPI tùy công nghệ.
- Chỉ hiển thị "Đã tải" sau khi xác nhận tệp tồn tại và tải trọn vẹn; cần chính sách kiểm tra khi người dùng di chuyển/xóa tệp ngoài ứng dụng.
- Khi đổi tài khoản, kết quả và thư mục cần ràng buộc rõ theo MST để tránh trộn hồ sơ của hai công ty.
- Chỉ đọc XML ở máy cục bộ nếu chưa có sự đồng ý truyền dữ liệu.
- Cần xác minh quy định và giới hạn truy cập eTax của cơ quan thuế trước khi tối ưu đa luồng / nhóm liên tiếp.

## 11. Cách triển khai an toàn

**Đợt 1 — Sửa UX trên luồng hiện có:**
- Chuẩn hóa ngày và cách sắp xếp; sửa nhãn, tách hai loại trạng thái, hiển thị nguyên nhân lỗi; tìm kiếm + trạng thái tải + xem chi tiết.
- Thêm test cho trạng thái "tra cứu xong nhưng chưa tải", "không chấp nhận nhưng vẫn có ZIP", "thành công GNT nhưng chưa lưu XML".

**Đợt 2 — Nâng cấp giao diện:**
- Thay layout, thanh điều kiện, bảng, drawer, tiến trình; thu gọn bộ lọc sau tra cứu.
- Phân ranh giới lớp UI và lớp nghiệp vụ (ETaxClient, QueryService, DownloadManager, FileStore, Logs) để không phải viết lại engine ổn định.

**Đợt 3 — Độ tin cậy và tính năng nâng cao:**
- Hàng đợi tải, thử lại có kiểm soát, chống trùng nội dung, khôi phục sau sự cố, import dữ liệu cũ, báo cáo nâng cao, parser XML theo schema.

## 12. Checklist nghiệm thu tối thiểu

- [ ] Không sắp xếp ngày `dd/MM/yyyy` bằng chuỗi.
- [ ] Không nhầm trạng thái thuế với trạng thái tệp.
- [ ] Tổng số "tìm thấy/đã tải/chưa tải/lỗi" khớp danh sách khi đổi tab/khoảng ngày.
- [ ] Tra cứu không tạo tệp; Tra cứu và tải có xử lý trùng.
- [ ] Sau khi tải lỗi người dùng biết lỗi ở hồ sơ nào, vì sao và có thử lại hay không.
- [ ] Tải 1 tệp, tải nhiều tệp, dừng, thử lại, tải nhóm liên tiếp đều có tổng kết.
- [ ] Chọn lại tài khoản không hiển thị hồ sơ của tài khoản trước.
- [ ] Các nút Mở thư mục/Mở tệp chỉ xuất hiện khả dụng khi đường dẫn/tệp thực sự tồn tại.
- [ ] Bảng hiển thị rõ ở 1080×700, 1366×768 và Windows scale 125%/150%.
- [ ] Có trạng thái rỗng, trạng thái đang chạy, thành công một phần và mất kết nối.
- [ ] Phân tích XML không gửi dữ liệu ra mạng ngoài ý muốn.
- [ ] Tính năng trong menu cũ đều có chỗ tương ứng hoặc được ghi rõ chính sách thay thế.

---

### Ghi chú về nguyên mẫu HTML

Tệp HTML là **bản trình diễn UX**, không phải sản phẩm sẵn sàng vận hành: dữ liệu, trạng thái kết nối, tải tệp và tài khoản đều mô phỏng. Có thể dùng nguyên mẫu để phản hồi bố cục/câu chữ/luồng thao tác trước khi triển khai UI trên framework Windows đang sử dụng.
