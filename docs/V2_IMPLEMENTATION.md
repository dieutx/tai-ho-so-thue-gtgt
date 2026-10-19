# Nâng cấp 1.1 → 2.0

Nguồn sự thật: working tree PySide6/Qt Widgets, gọi Python core in-process.
Đã đọc `prompt3.md`, đặc tả và ba ảnh trong `docs/design-v2`; HTML chỉ tham chiếu
bố cục/tương tác. Không đưa dữ liệu demo hoặc HTML runtime vào sản phẩm.

## Khảo sát và cách thay đổi

- `desktop/ui.py`: main window, bảng, settings, tài khoản, log và menu công cụ.
  Hiện bảng dùng chuỗi để sort; `_file_state` ghép vào trạng thái nghiệp vụ.
- `desktop/jobs.py`, `services.py`, `sessions.py`: QThread, CAPTCHA, session
  ETAX dùng chung, DVC riêng, gọi ba pipeline và bốn bước offline thật.
- `gdt_tax/{pipeline,gnt/pipeline,tb/pipeline}.py`: tải trong từng trang; GNT/TB
  cần form/ngữ cảnh trang tra cứu. Tải lựa chọn sẽ dùng chính vòng tra cứu này,
  chỉ gọi download cho ID đã chọn, tránh thay endpoint bằng phỏng đoán.
- Storage hiện có kiểm tra ZIP/XML/PDF, tên tệp và metadata. Lớp trình bày 2.0
  kiểm tra tệp bằng đường đọc, không rename/tạo file khi chỉ tra cứu.
- Duy trì CLI và format metadata bằng tham số tùy chọn có default cũ. GUI
  query không ghi catalog/attachment; selective download flush metadata đã xử lý.

Thứ tự: trạng thái/ngày/kiểm tra tệp → tải chọn lọc và lỗi theo bản ghi → bảng,
preset, điều kiện thu gọn, drawer → lịch sử/công cụ/XML → test/screenshot/build.
Giữ 4 nghiệp vụ, phiên tài khoản, DVC mặc định bật, cập nhật và xuất báo cáo.
Không tạo database thứ hai, không đổi schema tài liệu thuế hoặc công thức.

## Mốc 1.1 đã bảo quản

`.cache/optimization/release-1.1/source-1.1.zip` và EXE cùng thư mục là bản quay
lại trước thay đổi 2.0. EXE 88.256.580 B, SHA-256
`be8b860292caf5ef755a186db16da02870c5f3e7c1d7d51341abc89196a20a1a`.
433 test/6 skip, ruff và mypy 65 module PASS; native UI 15/15, frozen offline/OCR
hai lần PASS. Startup trung vị 4,072 s, RAM idle 168.087.552 B (3 lần).
Baseline workflow cũ timeout 180 s nên không công bố số so sánh workflow.
VM Windows sạch/RDP/DPI vật lý chưa kiểm chứng.

Mốc live được cấp phép trước đó: 5 DVC, 52 GNT, 5 thông báo tải hợp lệ; hồ sơ
thật chỉ ở `.cache`, không chuyển vào source, fixture, ảnh bàn giao hoặc EXE.

## Kiểm chứng và đối chiếu cuối

Đã triển khai và build Full 2.0.0: 460 test tổng/6 skip, không lỗi; ruff và
mypy core PASS. Native EXE 18 cấu hình và frozen offline/OCR hai lượt PASS.

| 1.1 | 2.0 |
|---|---|
| Thao tác theo cả khoảng | Checkbox, tải lựa chọn/chưa tải/lỗi, thao tác từng dòng |
| Trạng thái tệp ghép trạng thái thuế | Hai trạng thái riêng, xác minh tệp thực tế |
| Sort chuỗi | Datetime/Decimal; giữ âm/0/trống |
| Điều kiện luôn mở | Preset kỳ, thu gọn, giữ phạm vi query gốc |
| Dialog chi tiết | Drawer, copy mã, metadata, mở/tải |
| Báo cáo pipeline | Thêm xuất danh sách query rõ ràng, không mạng |
| Query ghi catalog | Query GUI không ghi tệp; tải/export mới ghi |

Mã chính: `v2_layout.py`, `v2_interactions.py`, `documents.py`, `table_model.py`,
`reports.py`; mở rộng services/jobs/sessions và tham số tùy chọn ba pipeline.
CLI giữ default cũ. Lỗi quyền ghi/khóa/hết đĩa có hướng dẫn, giữ tệp đã hoàn thành.
Sửa thêm liên kết nghiệp vụ/redirect/form legacy, một lần relogin hữu hạn.

Không đổi schema cấu hình/catalog, không cần migrate database. Bản 1.1 và source
rollback ở `.cache/optimization/release-1.1`; quay lại bằng EXE cũ với output riêng,
giữ nguyên dữ liệu gốc. Không ghi đè metadata hỏng.

Ảnh README/evidence chỉ có fixture. [Kết quả và SHA](DESKTOP_ACCEPTANCE.md),
[dung lượng](BUILD_SIZE_REPORT.md), [mapping](UI_FUNCTION_MAPPING.md).
Giới hạn: VM sạch/RDP/DPI vật lý chưa chạy; lịch sử RAM; chưa ký số. Chưa chạy lại
GNT/TB có tài khoản thật sau sửa redirect cuối, không tuyên bố đã PASS bước đó.
