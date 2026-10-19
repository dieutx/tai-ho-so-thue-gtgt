# Nghiệm thu desktop 2.0 — 19/10/2026

Full Windows x64, onefile/windowed, OCR tự động, version 2.0.0.0.
EXE **88,321,431 B (88.32 MB)**; chưa ký Authenticode.

SHA-256: `17e10d910f50610b5406d5e13088c7d29036ee5fa2da8d44e6f790515ad51c06`.

## Chức năng đã kiểm chứng

- Bốn tab, preset kỳ, điều kiện thu gọn, lọc và chọn nhiều dòng, khung chi tiết,
  lịch sử tác vụ và xuất danh sách Excel. DVC mặc định bật.
- Trạng thái nghiệp vụ độc lập trạng thái tệp; ngày sort theo datetime, số tiền
  theo Decimal. Kiểm tra ZIP CRC/XML/PDF và SHA-256 bằng đường chỉ đọc.
- Tra cứu GUI không ghi catalog/báo cáo/tệp đính kèm. Tải lựa chọn giữ đúng
  tài khoản, kỳ, nơi lưu của lần tra cứu; chỉ tải ID đã chọn, giữ hàng còn lại.
- ETAX dùng chung phiên; DVC có cookie riêng. HTTP 200 thiếu form/bảng báo lỗi rõ,
  không lặp sáu lần. Nhận diện liên kết nghiệp vụ, JS/meta redirect và form chuyển
  tiếp legacy; đăng nhập lại tối đa một lần khi trang nghiệp vụ không mở được.
- Retry hữu hạn WinError 5/32/33; lỗi hết đĩa, tệp khóa, thiếu quyền được giải thích.
  Lỗi ghi danh mục giữ hàng và tệp đã tải, không mở báo cáo cũ như kết quả mới.
- Phân tích XML/ZIP chọn tệp/thư mục hoặc kéo thả, không mạng/credential;
  giữ NEED_MAPPING/UNKNOWN/CONFLICT và các lần nộp.

## Kết quả chạy

| Kiểm tra | Kết quả |
|---|---|
| Unittest | 460 tổng, 454 đạt, 6 bỏ qua; không lỗi |
| Ruff / mypy core | PASS / PASS, 65 module |
| Native EXE UI | 18/18 cấu hình, 4 tab |
| Source UI | 18/18 cấu hình; 6 cấu hình có dữ liệu fixture và drawer |
| Frozen offline/OCR | Hai lượt PASS, socket bị chặn, mapping và OCR từ bundle |
| Bundle audit | 160 entry; 0 đường dẫn cấm; 0 secret khớp; 1 model ONNX; 5 mapping |
| Startup / RAM | Trung vị 15.114 s / 106,577,920 B, ba tiến trình mới |
| Workflow frozen 1.1 → 2.0 | 15.737 s → 15.896 s trung vị; 3 lần mỗi bản; cùng 15 declarations/5 MAPPED/PARTIAL |

Sáu kích thước 1920×1080, 1366×768, 1280×720, 1080×700, 1024×768,
1024×600 × scale 100/125/150%; trừ 40 physical px taskbar, kiểm tra frame/control.
Không đổi DPI Windows vật lý. [Bằng chứng](desktop-evidence/2.0/release-summary.json),
[frozen 1](desktop-evidence/2.0/report-1.json), [frozen 2](desktop-evidence/2.0/report-2.json),
[audit](desktop-evidence/2.0/bundle-audit.json).
[Số đo workflow](desktop-evidence/2.0/workflow.json).

## Kiểm thử cổng thật

Mốc 1.1 đã tải hợp lệ 5 DVC, 52 GNT, 5 thông báo; chạy lại giữ SHA-256.
Mốc 2.0 đã tra cứu lại 5/52/5, query không đổi tệp trên đĩa; tải chọn một hồ sơ
mỗi nhóm thành công, mỗi nhóm đúng một attachment POST. Chạy tiếp dùng lại tệp,
không POST attachment, giữ size/mtime; một ETAX login thành công, cookie DVC riêng.
Không khẳng định lượt 2.0 so sánh hash trước/sau: lượt này so sánh size/mtime.
Hồ sơ thật chỉ ở `.cache/optimization/live`, không trong ảnh, source hoặc EXE.

Sau sửa redirect/form legacy, đã chạy live error-path không credential và mock
redirect/auto-submit; **chưa chạy lại GNT/TB có tài khoản thật sau sửa cuối**.

## Giới hạn

- Windows 10/11 VM sạch, RDP, đổi màn hình/DPI vật lý: NOT RUN.
- Đúng ACL/OneDrive của ảnh người dùng và lỗi phá hủy trên tài khoản thật: NOT RUN;
  lỗi quyền ghi/khóa/hết đĩa/mất mạng được kiểm tra bằng fault injection.
- Lịch sử trong RAM tối đa 100 tác vụ; đọc catalog cũ qua menu dữ liệu cũ.
- Request/OCR/ghi tệp hiện tại đợi timeout hoặc hoàn tất trước khi dừng an toàn.
- Chưa ký số, chưa build Lite, Full chưa dưới 80 MB. Không tự cộng/chọn lần nộp.
- Baseline workflow 203 MB timeout 180 giây, không dùng làm số đo so sánh.

Vận hành: [BUILD_WINDOWS.md](../BUILD_WINDOWS.md). [Bản đồ chức năng](UI_FUNCTION_MAPPING.md).
