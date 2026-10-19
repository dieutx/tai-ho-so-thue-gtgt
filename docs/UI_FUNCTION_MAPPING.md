# Desktop: đối chiếu mã nguồn (19/10/2026)

Source of truth: checkout hiện tại, core 1.0.0 / desktop 2.0.0. Desktop gọi Python
in-process, không gọi executable CLI hoặc interpreter bên ngoài.

| Giao diện | Hàm thật và input | Output / trạng thái |
|---|---|---|
| Tờ khai: tra cứu / tải | `Pipeline(settings, http, captcha).run()`; `Settings.from_env(environ={}, env_file=None, **overrides)`, `from_date/to_date` dd/MM/yyyy, `download_dir`, `dry_run`, `case_id` | `RunSummary`: discovered/downloaded/expected/skipped_periods, `complete`, `search_complete`; ZIP, danh_sach_to_khai.xlsx, danh_sach_ho_so.csv/json, phan_loai_ho_so.json |
| GNT: tra cứu / tải | `GntPipeline(...).run()`; cùng Settings, không case_id; `gnt_periods` chia toàn khoảng theo ngày lập | XML, danh_sach_giay_nop_tien.csv/json/xlsx; GntSummary.discovered/downloaded/complete |
| Thông báo: tra cứu / tải | `TbPipeline(...).run()`; cùng Settings, không case_id; `tb_periods` chia toàn khoảng theo ngày gửi | PDF, danh_sach_thong_bao.csv/json/xlsx; TbSummary.discovered/downloaded/complete |
| Kiểm kê | `inventory.scan_directory(root, metadata_path=...)`, `write_manifest`, `build_discovery`, `write_discovery` | manifest_artifact.json, bao_cao_discovery.json/md; container/member errors giữ nguyên |
| Đọc XML | `parser.cli.parse_manifest(manifest, root, registry=load_registry())`, `write_parsed` | parsed_declarations.json, status MAPPED/NEED_MAPPING/error; giữ artifact, hash, XPath và mọi lần nộp |
| Phân loại | `classify.classify_manifest(manifest)`, payload như CLI, ghi JSON nguyên tử | phan_loai_artifact.json, OK/UNKNOWN/CONFLICT |
| Xuất Excel | `export.build_rows`, `filter_rows`, `build_workbook`, `write_workbook` | Tax_Return_Summary.xlsx; bộ lọc tax_group/form_code/form_version/period/filing_type/status; CSV bổ sung qua write_csv |
| Offline toàn bộ | Bốn stage trên theo thứ tự; manifest/parsed/classification nằm trong thư mục kết quả, root XML luôn là nguồn | Không mạng, không credential; thiếu dependency phải báo lỗi, không tự dùng output cũ của job khác |
| CAPTCHA | `GuiCaptchaSolver` → `DdddOcrSolver.solve(bytes)` | Model `common_old.onnx`, `beta=False`; tối đa 5 lần tự động thất bại mới nhập tay; rỗng/lỗi trả vòng retry lấy ảnh mới; nhận feedback đăng nhập/tra cứu, thành công reset; hủy được |
| Kết nối | Settings.request_timeout/http_retries/login_attempts/search_attempts/pause_between_records/pause_between_pages/pause_jitter/max_days_per_search/page_size/header_profile/proxy_url/extra_headers | HTTP TLS giữ mặc định; không dump HTTP trong desktop; thông số nhạy cảm chỉ ở phiên |
| Tiếp tục | ZipStore/GntStore/TbStore.find_existing và writer metadata hiện có | Reuse file hợp lệ; downloaded của core gồm cả file reuse, UI ghi rõ điều này |

CLI tải: 0 OK, 1 INCOMPLETE (bao gồm DVC bị tắt), 2 CONFIG_ERROR.
Offline CLI: 0 kể cả NEED_MAPPING và một số lỗi artifact đã ghi trong JSON;
1 khi GdtError. Desktop giữ output nhưng biểu diễn PARTIAL nếu có lỗi hoặc
NEED_MAPPING/UNKNOWN/CONFLICT, không suy luận 0 là mọi mẫu đã được phân tích.

Chính sách tờ khai lấy từ Settings.periods/source_enabled. Desktop bật DVC mặc định;
CLI vẫn tắt mặc định. Nếu DVC lỗi trong khoảng qua cutoff, giữ phần ETAX đã xử lý.
cutoff 01/07/2025; GNT/TB không dùng cutoff. Khoảng dài do backend tự chia ≤31 ngày.
`case_id` không tồn tại trong CLI GNT/TB. Parser không parse chỉ tiêu GNT hoặc PDF.

Đã đọc README, cấu hình mẫu, ARCHITECTURE, REVIEW, core pipeline/HTTP/storage,
GNT/TB, CAPTCHA, inventory/parser/classify/export, registry và test/fixture.
Tham chiếu HDDT local: MainWindow.xaml, AdvancedSettings.xaml,
Start-HddtGui.ps1, Build-WindowsApp.ps1. Khác prompt: HDDT hiện là 1160×768,
min 880×560, palette #F4F6FA/#14243D; dùng accent #2563EB. Desktop thuế dùng
palette compact trong prompt, không kế thừa kích thước tối thiểu của HDDT.

Core trước nâng cấp chưa có callback cancellation/progress. Bổ sung RunHooks
tùy chọn; mặc định không thay CLI. Callback record chỉ phát sau ghi metadata;
request/retry/pause kiểm tra token, ghi file nguyên tử hoàn tất trước khi dừng.
Offline kiểm tra token giữa container/artifact/stage; không hủy giữa ghi workbook.
Request đang gửi đợi timeout; OCR native đang xử lý đợi kết thúc inference.

Giới hạn sẵn có giữ nguyên: danh mục core có thể gộp dữ liệu nhiều lần chạy;
UI chỉ hiện records của job hiện tại. Nên dùng output riêng mỗi tài khoản.
Đã tải thật DVC/GNT/TB ngày 19/10/2026; phạm vi và số đếm ở DESKTOP_ACCEPTANCE.md.

| Tiện ích desktop 1.1 | Entry point / kết quả |
|---|---|
| Tài khoản chung | `AccountDialog` → `AccountContext` → `ETaxSessionManager`; bí mật trong RAM, phiên ETAX tuần tự; đổi tài khoản xóa cookie/DSE |
| Tải nhiều nhóm | `Worker.run` → manager.execute tuần tự; kết quả từng nhóm giữ trong `JobResult.children`, dừng giữ nhóm đã xong |
| Dữ liệu cũ | `migration.load_saved`; đọc catalog không cần mạng/tài khoản, sao chép ZIP/XML/PDF hợp lệ khi chọn chuyển dữ liệu |
| Phiên bản/cập nhật | `UpdateChecker` / `release_message`; GET public releases riêng với tax session, chỉ theo thao tác người dùng, không tự tải/cài |
| Lỗi ghi Windows | `atomic.replace_with_retry`; retry hữu hạn WinError 5/32/33, lỗi dai dẳng báo thao tác khắc phục, giữ rows/tệp đã tải |

## Giao diện 2.0

Bảng pipeline phía trên mô tả output khi tải; query GUI không ghi output.

| Giao diện | Entry point | Hành vi |
|---|---|---|
| Tra cứu | `services.run_online`, `persist_metadata=False` | Đọc danh sách, không tạo catalog/attachment/report |
| Tải chọn/chưa tải/thử lại | `v2_interactions` → Worker → session manager → pipeline `target_ids` | Chỉ tải ID mục tiêu trong ngữ cảnh query gốc, giữ hàng còn lại và kết quả đã xong |
| Kiểm tra tệp | `documents.verify_rows` qua Worker | Chỉ đọc, kiểm ZIP CRC/XML/PDF và SHA-256; không rename |
| Xuất danh sách Excel | `reports` qua Worker | Workbook người dùng chọn; không mạng/đăng nhập, escape công thức |
| Chọn/sort/lọc | `table_model` | Datetime/Decimal, checkbox chỉ các dòng hiện, counters theo query |
| Chi tiết | `v2_interactions.details` | Metadata gốc, copy mã đầy đủ, mở/tải đúng tệp |
| XML/ZIP chọn | `inventory.scan_directory(selected_paths=...)` | Không quét ngoài nguồn chọn, giữ pipeline offline cũ |
| Lịch sử | `v2_interactions.show_history` | 100 tác vụ trong RAM; catalog cũ qua menu dữ liệu cũ |

Tách `_file_status` khỏi `trang_thai`; thông báo đã xem/tờ khai từ chối không phải
lỗi tải. Đổi tài khoản xóa dataset/drawer/selection/filter/query cũ.
