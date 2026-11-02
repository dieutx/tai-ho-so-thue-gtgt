# Kho hồ sơ local 2.1.0

Thanh chọn kỳ, Từ/Đến và nút tra cứu luôn hiện. Chọn kỳ là đọc local; Tra cứu hỏi cổng thuế rồi bổ sung metadata. Tra cứu và tải kiểm tra tệp đã có và tải phần thiếu. Kỳ đã tra cứu vẫn có thể tra cứu lại để tìm hồ sơ bổ sung. Không có thao tác tự xóa hồ sơ khi online trả ít hơn hoặc lỗi.

`Kho` là toàn bộ hồ sơ của tài khoản/nghiệp vụ, `Kỳ đang xem` là khoảng ngày hiện tại. Ngày lọc: tờ khai=ngày nộp, GNT=ngày lập, thông báo=ngày gửi. Hồ sơ thiếu ngày nằm ở checkbox `Ngày chưa xác định`, không tự lẫn vào mọi kỳ. Tìm kiếm/CQT/trạng thái tiếp tục lọc local. `Tải chưa tải` chỉ áp dụng các hồ sơ của kỳ đang chọn; ứng dụng sẽ yêu cầu đăng nhập online khi cần.

`Xem hồ sơ đã lưu` cho phép nhập tên tài khoản để đọc kho trên máy mà không đăng nhập cổng thuế. Đây là quyền truy cập local của người đang dùng Windows, không chứng minh phiên online. Folder và RecordKey đều phải khớp fingerprint. Dữ liệu không có owner không được tự gán tài khoản theo tên thư mục; vẫn mở được bằng luồng phân tích offline/chuyển dữ liệu cũ hiện hữu.

DB v1: `ROOT/<account-namespace>/to-khai/catalog.sqlite3`, `gnt/catalog.sqlite3`, `thong-bao/catalog.sqlite3`; nếu namespace cũ chưa có owner thì giữ policy `tai-moi/<nghiep-vu>`. Phân DB theo workspace nghiệp vụ để dùng chính manifest ownership đã có, không gán owner cho folder cha chứa nhiều nhánh legacy. Khóa gồm account+mode+RecordKey(account/source/kind/remote ID). File ZIP/XML/PDF và evidence ở ngoài DB. DB không nằm trong EXE hay `_MEIPASS`.

Lần mở local đầu tiên import JSON đã xác minh owner; lưu fingerprint migration và DB backup. Các lần online ghi tăng dần trực tiếp SQLite; JSON/CSV/XLSX là export tương thích. Không lấy JSON mới để replace DB. JSON đã import không tự ghi ngược metadata cũ lên DB ở lần mở sau. CLI core giữ dry-run không ghi; JSON do công cụ ngoài chỉnh sau migration cần reconciliation rõ ràng qua repository API `import_json(..., reconcile=True)`, không tự quét/nhận lại.

File trong view chỉ stat size/mtime đã ghi sau verify; không rehash toàn kho khi đổi ngày. File không có evidence verify, bị xóa, đổi size/mtime hoặc đã biết invalid không được hiển thị đã tải. `Kiểm tra tệp` thực hiện deep verify và cập nhật SQLite. Tệp chính và attachment có registry riêng; ZIP hợp lệ không khẳng định đã đủ thông báo.

Đổi `Nơi lưu` mở workspace tương ứng, không chuyển/xóa dữ liệu cũ. Quay về root cũ sẽ đọc lại DB cũ. Ưu tiên ổ local; SQLite dùng rollback journal (không bật WAL). Network share/OneDrive vẫn phụ thuộc khóa file và chính sách đồng bộ; nên đóng app trước khi copy/backup folder, không dùng một DB đang mở từ nhiều máy.

## Kiểm tra và phục hồi

Đọc counts/integrity, không in metadata nhạy cảm:

```powershell
.venv-release/Scripts/python.exe scripts/inspect_local_catalog.py 'ROOT/account/to-khai/catalog.sqlite3'
```

Trước migration, SQLite backup API tạo `catalog.backup-<id>.sqlite3`; file JSON và ZIP/XML/PDF gốc được giữ. Khi cần rollback: đóng mọi bản ứng dụng; sao chép toàn workspace sang nơi an toàn; đổi tên DB hiện tại để giữ bằng chứng; copy backup đã kiểm tra `integrity_check=ok` thành `catalog.sqlite3`. Không xóa DB mới: nếu đã có discovery mới sau backup, cần đối soát lại để lấy phần bổ sung. Có thể dùng EXE cũ trên bản sao workspace với JSON exports; EXE cũ không hiển thị metadata chỉ có trong SQLite từ thao tác Tra cứu của 2.1.0.

Không reset database để xử lý lỗi. Với schema mới hơn ứng dụng hoặc DB integrity lỗi, app dừng đọc/ghi và giữ file để phục hồi. Quarantine giữ metadata có xung đột/missing owner/path ngoài root; không tự sửa identity. Số `Cần xác minh định danh` nằm ở tooltip counts; chưa có màn hình chỉnh sửa quarantine.
