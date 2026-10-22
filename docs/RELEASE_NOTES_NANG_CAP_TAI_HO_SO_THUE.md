# Release notes — Nâng cấp trải nghiệm Tờ khai / Phản hồi CQT / Thông báo thuế

**Ngày:** 22/10/2026  
**Phạm vi:** source desktop + test + **EXE local để test** (chưa ký số/publish)  
**Kế hoạch gốc:** `MASTER_PLAN_NANG_CAP_APP_TAI_HO_SO_THUE.md`

## 1. Tóm tắt

Đợt nâng cấp tách rõ ba khái niệm trước đây bị trộn trong UI:

1. **Tờ khai / lần nộp** — dữ liệu hồ sơ.
2. **Phản hồi CQT của tờ khai** — thông báo đính kèm trong `thong-bao-dinh-kem/<mã hồ sơ>/`.
3. **Thông báo thuế độc lập** — tab riêng, tải PDF từ trang Thuế điện tử cũ.

Tab Tờ khai không còn hiển thị `Chấp nhận / Mở N tệp`. Cột mới **Phản hồi CQT** chỉ mở bảng phản hồi của đúng lần nộp; cột **Trạng thái CQT** và **Trạng thái tải** là hai trạng thái độc lập. XML được xem trong ứng dụng với hai chế độ, parser an toàn, không sửa byte gốc.

## 2. Thay đổi chính

### Tab Tờ khai

- Cột `Thông báo` → **`Phản hồi CQT`**, hiển thị `Xem phản hồi (N)` hoặc `Chưa có phản hồi`.
- Cột `Trạng thái thuế` → **`Trạng thái CQT`**; ưu tiên bằng chứng phản hồi, fallback trạng thái cổng, không suy ra từ tệp đã tải.
- Cột `Tệp ZIP` → **`Trạng thái tải`**.
- Nhãn khoảng tra cứu dùng **Ngày nộp** (không gọi là "Kỳ"); `Kỳ tính thuế` là cột riêng.
- Tìm kiếm **không dấu/không phân biệt hoa-thường**; lọc riêng **trạng thái CQT**, **trạng thái tải**, **loại thông báo** (chỉ giá trị thực có).
- Hiển thị `Hiển thị X/Y`; lưu filter/sort/độ rộng cột theo tab trong `settings.json` (`ui_state`).

### Bảng phản hồi con

- Mở từ `Xem phản hồi (N)` hoặc menu chuột phải; panel nằm dưới bảng chính (không popup lồng popup).
- Cột: STT, Loại phản hồi, Số/Mã thông báo, Ngày thông báo, Ngày nhận, Kết quả, XML.
- Mỗi dòng mở đúng `asset_key`; có `Lưu tệp`, `Mở bằng ứng dụng`, `Mở thư mục`, `Thông tin kỹ thuật`.
- Empty state nói rõ "Chưa có phản hồi trong dữ liệu hiện có" — không kết luận cổng không có thông báo.

### XML Viewer

- Hai tab: **Nội dung dễ đọc** (default) và **XML gốc**.
- Parser `lxml` an toàn: không resolve entity/DTD, không mạng, trần 8 MiB; raw dùng `QPlainTextEdit` (không render HTML/script).
- Header theo `source_kind` (Phản hồi CQT / Thông báo thuế); giữ `owner_kind + owner_key + asset_key`.
- Hành động: Sao chép XML, Lưu XML/tệp, Mở bằng ứng dụng, Đóng. Không ghi đè tệp gốc; không sửa byte gốc.
- PDF/ZIP và XML lạ: nêu "Chưa hỗ trợ trình bày nội dung này", vẫn xem raw và mở bằng ứng dụng.

### Tab Thông báo thuế

- Cột riêng: Loại/Tên thông báo, Số thông báo, Ngày gửi, Cơ quan phát hành, Trạng thái xem, Trạng thái tải, Thao tác.
- `Xem tệp` dùng XML Viewer với `source_kind=tax_notice`; **không** dùng selector phản hồi tờ khai.
- `trang_thai` của tab này là trạng thái xem, không phải kết quả CQT.

### Chẩn đoán, tải và xuất

- Drawer tách **Thông tin kỹ thuật** (đường dẫn, dung lượng, SHA-256, nguồn, toàn vẹn) khỏi thông tin nghiệp vụ; có nút sao chép.
- Trạng thái tải và toàn vẹn tách biệt: `not_checked/unverified/invalid`; hash không được gọi là chữ ký số.
- Gợi ý xử lý lỗi theo nhóm: phiên hết hạn, 429, mạng, quyền/dung lượng, tệp sai định dạng, hồ sơ không còn trong kết quả.
- Tiến trình đạt 100% khi SUCCESS/PARTIAL/LOADED, reset khi job mới; retry chỉ chọn dòng lỗi, giữ tệp hợp lệ.
- **Xuất hồ sơ ZIP**: `to-khai/`, `phan-hoi/`, `manifest.json`; chỉ phản hồi của đúng lần nộp; chống ZIP slip/trùng tên/ghi đè; ghi rõ tệp thiếu.
- **Đối soát**: bảng theo lần nộp, icon ✓/✕/? và tô đỏ dòng từ chối; xuất **CSV UTF-8 BOM** hoặc **XLSX** (sheet `Đối soát` + `Phạm vi`), chống formula injection.
- Lịch sử phiên có cột **Tìm thấy** và nút **Thử lại mục lỗi** (cùng tab/tài khoản).

## 3. Dữ liệu và migration

- **Không có DB**, không đổi schema, không đổi định dạng tệp tải về.
- Không tạo/di chuyển/xóa tệp người dùng; sidecar `.integrity.json` chỉ được đọc.
- `settings.json` thêm khóa `ui_state` (filter/sort/độ rộng cột); không chứa rows/result/credential.
- Có thể xóa `ui_state` trong `settings.json` để reset giao diện.
- Rollback: revert các file source trong release notes; dữ liệu tải và metadata cũ giữ nguyên.

## 4. Kiểm thử đã chạy

| Gate | Kết quả |
|---|---|
| `python -m unittest discover -s tests -t .` | **617 tests, OK, 7 skip** (OCR/identity tùy chọn) |
| `python -m ruff check .` | Pass |
| `python -m mypy gdt_tax` | 67 file, 0 issue |
| `python -m desktop.main --ui-check` offscreen | Pass ở 1366×768, 1024×600, 853×480 |
| Preview offscreen | Bảng Tờ khai, panel phản hồi, XML Viewer, tab Thông báo thuế |
| `scripts/build_windows.ps1` | Exit 0; PyInstaller onefile, audit bundle pass, frozen offline smoke pass |

### EXE đã build để test

- **Bản test:** `dist/TaiHoSoThue-Windows-upgrade-20261022.exe`
- Bản canonical cùng build: `dist/TaiHoSoThue-Windows.exe`
- Kích thước: **88.432.597 byte**
- SHA-256: **`85D582FF90070B81FD56C458102A4DCDBAE7280E3CB088C6F9005D57BFD72584`**
- Version: **2.0.0** (FileVersion 2.0.0.0)
- Gate đã chạy trên artifact: **617 tests**, ruff, mypy 67 file, audit bundle (0 forbidden/secret), smoke offline đóng băng 2 lượt + GUI + **18/18 UI/DPI** (6 kích thước × 3 scale).
- Bản canonical cũ 2.0.3 được backup tại `.cache/optimization/TaiHoSoThue-Windows-before-upgrade-20261022.exe`.
- **Lưu ý:** EXE build từ **working tree chưa commit**. Nếu phát hành chính thức, cần commit đúng source, build lại và chạy gate online/sign/publish.
**Chưa chạy:** ký số, publish release, kiểm thử online bằng tài khoản thật. Các bước này cần pipeline release và xác nhận của chủ dự án.

## 5. Giới hạn / rủi ro còn lại

- Checkout gốc **chưa có composite key tài khoản+nguồn** (`gdt_tax/identity.py` chỉ có ở checkout tích hợp). Ownership hiện dựa thư mục mã hồ sơ; UI truyền `taxpayer_key` khi mở panel/viewer nhưng `verify_rows` đọc sidecar với `parent_key=''`.
- Sidecar `.integrity.json` được đọc nhưng **chưa được ghi** ở checkout gốc; đa số tệp là `LEGACY_UNVERIFIED` → integrity `unverified`.
- Lịch sử tải và resume queue là **session-only**; chạy lại dựa vào `find_existing` để bỏ qua tệp hợp lệ.
- Multi-MST **DEFER** (D-013): app hỗ trợ chuyển tài khoản tuần tự, dữ liệu/file/history tách theo tài khoản; chưa hỗ trợ nhiều phiên đồng thời.
- `mypy desktop/documents.py` có lỗi pre-existing (`naming(record)`) ngoài gate CI `mypy gdt_tax`.
- Tệp XML > 8 MiB không hiển thị toàn bộ trong viewer; dùng mở bằng ứng dụng/lưu tệp.
- Không suy đoán hồ sơ quá hạn/chấp nhận khi thiếu bằng chứng.

## 6. File chính đã thay đổi

**Mới:** `desktop/domain.py`, `desktop/feedback_service.py`, `desktop/feedback_panel.py`, `desktop/xml_viewer.py`, `desktop/bundle.py`, `desktop/reconciliation.py`; test tương ứng.

**Cập nhật:** `desktop/documents.py`, `desktop/table_model.py`, `desktop/v2_layout.py`, `desktop/v2_interactions.py`, `desktop/ui.py`, `desktop/state.py`, `desktop/settings_store.py`, `desktop/errors.py`, `desktop/reports.py`, `desktop/notice_reports.py`, `tests/test_desktop_v2.py`, `tests/test_desktop_notices.py`, và file master plan.

## 7. Đối chiếu Acceptance Matrix

Các nhóm AC01–AC25 được phủ bởi: `tests/test_feedback_contract.py`, `tests/test_feedback_service.py`, `tests/test_table_feedback_column.py`, `tests/test_xml_viewer.py`, `tests/test_notice_module.py`, `tests/test_search_and_state.py`, `tests/test_download_integrity.py`, `tests/test_bundle_export.py`, `tests/test_reconciliation.py`, `tests/test_desktop_v2.py`.
