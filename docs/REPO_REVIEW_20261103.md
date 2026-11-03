# Rà soát và hợp nhất bản Windows 2.1.4 — 03/11/2026

## Nền mã và phạm vi

GitHub `main` tại `0c7ab32` và nhánh local `fix/personal-dvc-login` tại
`b744d22` đã tách lịch sử. Hợp nhất bằng merge, không reset/rebase các bản sửa
2.1.2/2.1.3, không thay các tag cũ bị khác SHA giữa GitLab và GitHub.

Rà soát các đường tích hợp config/CLI → xác thực/định tuyến → portal/pipeline →
lưu và kiểm tra tệp → SQLite/desktop; đọc cấu hình dependency, spec PyInstaller,
build/smoke/provenance và workflow GitHub. Bộ kiểm thử toàn repo bao phủ thêm
parser/mapping, kiểm kê, xuất Excel, định danh, migration, HTTP và giao diện.
Đây là rà soát mã và hồi quy offline; không đối chiếu pháp lý từng chỉ tiêu,
không đăng nhập tài khoản thuế thật trong lượt này, không chứng nhận mọi biến thể cổng.

## Phát hiện và sửa

| Vấn đề | Sửa và kiểm chứng |
|---|---|
| Hai nhánh cùng thêm `--account-type`/keyword, một nhánh ép CN sang legacy cho mọi ngày | Bỏ khai báo trùng; CLI tôn trọng DVC/cutoff và biến môi trường. Test gọi CLI thật tới bước khởi tạo solver, dừng trước HTTP. |
| ZIP thông báo được core lưu đúng nhưng desktop chỉ xác minh kiểu tờ khai | Dùng chung `required_document_kind` cho save/resume/desktop. Test ZIP XML thông báo, cả metadata NOTICE và tiêu đề 04/SS; ZIP thông báo vẫn bị từ chối cho hồ sơ tờ khai thường. |
| Retry SystemError/HTTP 200 Too Many Requests dùng `time.sleep` trực tiếp | Chờ qua `RunHooks.pause`, nhận hủy và ngân sách chạy; test bảo đảm không gửi request tiếp sau khi hủy. |
| XLSX chỉ kiểm tra tên member/size, chưa CRC và chưa xác minh XML workbook | Dùng kiểm tra ZIP giới hạn tài nguyên/CRC, từ chối member trùng, xác minh root/namespace XML cấu trúc. Test workbook thật, CRC hỏng, workbook giả, vượt số member. |
| Một nhóm local lỗi nhưng tổng hợp báo LOADED | Trả PARTIAL và số nhóm lỗi, giữ các dòng đọc được. |
| Ảnh UI ở 1024×560/150% có hướng dẫn trống đè lên tiêu đề bảng | Ẩn tiêu đề khi danh sách trống, hiện lại khi có hồ sơ; test vòng chuyển trống/có dòng. |
| Đọc mtime ngoài khối xử lý lỗi I/O | Đọc stat một lần trong khối xử lý lỗi; tệp không đọc được chuyển sang chưa tải, không làm mất danh mục. |
| Metadata đã commit ghi phiên bản/SHA của build cũ | Phiên bản duy nhất ở `desktop/__init__.py`; bỏ theo dõi hai tệp sinh tự động, build tạo metadata từ commit hiện tại. |
| Biến môi trường onedir có thể đổi kiểu build phát hành; CI chỉ giữ EXE | Buộc onefile trong script, khôi phục biến môi trường sau build; CI kiểm tra tag khớp version và giữ EXE/checksum/manifest. |

Các sửa trên GitHub được giữ: nhận mật khẩu sai DVC trả HTTP 200/status 401,
giải mã ZIP JSON/base64, tệp thông báo TBTNhan/THONGBAO/XLSX, xác nhận đăng nhập
đồng thời và phân trang cá nhân, nhận kỳ rỗng và hồ sơ không có tệp đính kèm.
Các sửa local được giữ: DVC cá nhân từ cutoff, cookie riêng và khôi phục bảng
cá nhân từ kho `ca-nhan`, không lẫn dữ liệu doanh nghiệp.

## Kiểm chứng

- `scripts/run_test_gate.py --profile desktop`: 1.002 test, PASS, 6 skip
  (EasyOCR/PaddleOCR và lớp solver test nền; ddddocr/Qt bắt buộc đã chạy).
- `ruff check .`: PASS.
- `mypy gdt_tax tests/test_core_contracts.py`: PASS, 95 source files.
- `git diff --check`: PASS.
- GitHub Windows runner dùng đường dẫn TEMP dạng tên ngắn 8.3; test reuse
  so sánh đường dẫn đã resolve để nhận đúng cùng một tệp, không phụ thuộc alias.
- Quy trình phát hành tiếp tục chạy lại gate trên commit chốt, kiểm tra inventory,
  audit bundle, source/frozen OCR, hai lượt standalone offline và 18 cấu hình UI.
  Kết quả gắn với EXE nằm trong `release-manifest.json`, `SHA256SUMS.txt` và
  ghi chú của [release 2.1.4](https://github.com/dieutx/tai-ho-so-thue-gtgt/releases/tag/desktop-v2.1.4).

Giấy nộp tiền cá nhân vẫn báo chưa hỗ trợ vì chưa có lệnh tải đã xác minh.
EXE chưa ký Authenticode; smoke trên máy build không thay cho nghiệm thu
Windows 10/11 sạch hoặc kiểm thử cổng bằng tài khoản thực.
