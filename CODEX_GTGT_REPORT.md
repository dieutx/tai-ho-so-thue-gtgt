# Báo cáo tiếp tục nâng cấp và sửa Tra cứu GTGT

Ngày: 03/11/2026. Base HEAD: `be65225847655c97224a91a3be33100809130883`.
Thay đổi trong báo cáo nằm ở working tree, chưa commit/push/deploy/release.

## 1. Công việc hoàn thành

- Đọc README, PROGRESS, tiến độ triển khai 2.1.0, cấu hình/gate kiểm thử, lịch sử Git gần nhất và kế hoạch bàn giao AUTH/tăng tốc/XML.
- Không tìm thấy `AGENTS.md` hoặc file TODO trong root và các thư mục mã nguồn/kiểm thử đã kiểm tra. Công việc còn lại được đối chiếu từ các file kế hoạch/tiến độ.
- Trước sửa, working tree chỉ có file chưa theo dõi `PLAN_FIX_AUTH_TANG_TOC_XEM_XML_SESSION_TIEP_THEO.md`. Giữ nguyên file này; không reset/clean, không sửa worktree phụ hoặc dữ liệu đã tải.
- Tiếp tục hoàn thiện luồng local-first đang triển khai: cập nhật bảng từ SQLite đúng khoảng ngày hiện tại, giữ lịch sử các khoảng khác, giữ kết quả tác vụ và báo lỗi cập nhật kho.
- Lần theo nút Tra cứu, cấu hình ngày, worker/session, pipeline, API adapter, phân trang, checkpoint SQLite và bước cập nhật bảng.
- Viết regression trước khi sửa: **6/6 kiểm thử mới tái hiện lỗi** (5 assertion failures, 1 DatabaseError). Sau sửa, mở rộng thành 13 kiểm thử mới, đều đạt.

## 2. Nguyên nhân và bằng chứng về 128/128

### Đã xác nhận trên source và dữ liệu giả lập

1. `desktop/v2_layout.py` nối **Tra cứu** với `start(True)` và **Tra cứu và tải** với `start(False)`. `make_config()` lấy khoảng ngày hiện tại; adapter gửi các tham số ngày qua GET/POST của cổng, không có một API chung riêng cho nút này.
2. Trước sửa, `on_progress()` hiển thị `downloaded/discovered`. `discovered` chỉ là số hồ sơ đã gặp tới thời điểm đó, không phải tổng cuối cùng của toàn bộ các trang/khoảng ngày. Vì vậy **128/128 không chứng minh tác vụ đã hoàn tất và không phải giới hạn 128 hồ sơ**. Sau hồ sơ cuối, worker còn kiểm tra tệp, ghi danh mục và trả kết quả. Nút Tra cứu thuần túy trong source hiện tại vốn hiển thị “Đang tra cứu”, nên chưa thể xác định nút/bản EXE của ca người dùng chỉ từ chuỗi “Đang tải 128/128”.
3. `on_completed()` gán kết quả tác vụ rồi gọi `apply_local_date_filter()`. Hàm này thay toàn bộ `self.result` bằng một `JobResult` của kho local (`operation=library`, thường `state=LOADED`). **Trạng thái SUCCESS/ERROR/PARTIAL/CANCELLED, mã lỗi và ngữ nghĩa “đã tra cứu kỳ này” bị mất** dù các dòng SQLite vẫn tồn tại. Trường hợp thành công rỗng còn quay về lời nhắc chưa tra cứu online.
4. Nếu đọc kho thất bại, `apply_local_date_filter()` báo lỗi nhưng `on_completed()` tiếp tục ghi đè bằng thông báo hoàn tất. `catalog_view()` chưa bắt `sqlite3.Error`. Nhánh thông báo online cũng ghi lại status bằng plain text, làm mất liên kết **Xem chi tiết** của lỗi/partial.
5. Người dùng có thể đổi khoảng ngày lúc worker đang chạy. Source chủ đích giữ khoảng đang xem, nhưng thông báo hoàn tất không phân biệt khoảng vừa tra cứu với khoảng đang xem. Nhóm “Ngày chưa xác định” và bộ lọc bảng cũng có thể làm kết quả nhìn như không đổi.

### Cách sửa

- Dùng SQLite cung cấp các dòng, số hồ sơ trong kho và số ngày chưa xác định; giữ trạng thái/mã lỗi của tác vụ nếu đúng tài khoản, nơi lưu và khoảng ngày đang xem.
- Đọc kho trước khi thay bảng; lỗi đọc không ghi đè bảng bằng các dòng thô có thể thuộc khoảng cũ. Báo hoàn tất một phần nếu online xong nhưng cập nhật kho thất bại; giữ lỗi trong tổng kết/lịch sử và liên kết chi tiết.
- Hiển thị số hồ sơ đã tìm thấy và số tệp hoàn tất, bỏ mẫu số tổng chưa xác nhận. Phát trạng thái riêng khi kiểm tra tệp/hoàn tất danh mục.
- Tổng kết nêu khoảng vừa tra cứu; nếu đã đổi ngày, nêu thêm khoảng đang xem. Nêu rõ nhóm ngày chưa xác định/bộ lọc đang áp dụng. Online trả rỗng nhưng còn hồ sơ local thì nói rõ đang xem hồ sơ đã lưu, không xóa lịch sử.
- Cho status xuống dòng và giữ đầy đủ thông tin trong tooltip.
- Giữ xử lý phân trang hiện có: tiếp tục qua trang 3 sau hồ sơ 128; trang lặp phải báo lỗi thay vì kết luận đủ. Không đổi endpoint, giới hạn cổng, quy tắc chọn nguồn, CAPTCHA hoặc quy tắc tính thuế.

### Giới hạn kết luận

**Chưa tái hiện phiên online/EXE cụ thể của người dùng.** Chưa có phiên bản EXE, khoảng ngày và log đã che dữ liệu của lần 128/128. Các nguyên nhân trên được chứng minh bằng source và regression; không khẳng định đó là toàn bộ nguyên nhân của phiên người dùng, cũng không suy đoán cổng đã đổi API hoặc dữ liệu bị mất.

## 3. File sửa/tạo

| File | Nội dung |
| --- | --- |
| `desktop/library.py` | Chuyển lỗi SQLite thành kết quả đọc kho ERROR/PARTIAL, giữ nguyên DB để phục hồi. |
| `desktop/services.py` | Phát progress cho bước kiểm tra tệp/hoàn tất danh mục. |
| `desktop/v2_interactions.py` | Giữ outcome tác vụ, cập nhật đúng view, bảo toàn bảng khi đọc kho lỗi, sửa progress/tổng kết/liên kết lỗi. |
| `desktop/v2_layout.py` | Cho thông báo trạng thái xuống dòng. |
| `tests/test_lookup_completion.py` | 13 regression về completion, lỗi kho, nhiều khoảng ngày, trên 128 hồ sơ, trang lặp và dữ liệu lưu. |
| `CODEX_GTGT_REPORT.md` | Báo cáo này. |

## 4. Kết quả kiểm thử

- Baseline trước sửa: **911 tests, 904 đạt, 6 skipped, 1 error**. Error ở cleanup thư mục tạm của `test_save_only_successful_login_when_requested_and_mst_click_opens_menu`: Windows `WinError 145` (directory not empty). Đây là test có sẵn; không sửa/xóa dữ liệu để né lỗi. Các lượt full gate tiếp theo không tái hiện lỗi cleanup này.
- Regression trước sửa: `.cache/gtgt-regression-before.log`, 6/6 thất bại như mô tả trên.
- Regression cuối: `python -m unittest tests.test_lookup_completion -q`: **13/13 đạt**; `.cache/gtgt-lookup-tests.log`.
- Full desktop gate cuối: **924 tests, 918 đạt, 6 skipped, 0 failures/errors; PASS** trong 62,375 giây. Bốn skips do chưa cài EasyOCR/PaddleOCR tùy chọn, hai skips của lớp smoke solver cơ sở chưa cấu hình backend; gate yêu cầu Qt/default OCR vẫn đạt. Lệnh `.venv-release/Scripts/python.exe scripts/run_test_gate.py --profile desktop`, Qt offscreen; log `.cache/gtgt-final-tests.log`, kết quả cấu trúc `.cache/ci/desktop.json`.
- `ruff check .`: PASS. `mypy gdt_tax tests/test_core_contracts.py`: PASS, 93 source files. `git diff --check`: PASS.
- Tờ khai/GNT/thông báo: giả lập **129 hồ sơ × 2 khoảng tháng = 258 hồ sơ**, đủ các trang 1/2/3; trang thứ 3 lặp sau 128 hồ sơ phải báo SearchError.
- Kiểm thử dịch vụ thật `run_online()` với portal/HTTP giả: query 01–02/2025, mỗi tháng 129 hồ sơ, không gọi mạng và không tải tệp; chọn lại từng tháng đúng 129 hồ sơ; chạy lại không tạo bản ghi mới; SQLite integrity `ok`.
- Kiểm thử UI: SUCCESS/ERROR/PARTIAL, rỗng có xác nhận, lỗi kho, kết quả về muộn sau đổi tháng, bộ lọc còn hiệu lực, query sau khi xem thư mục cũ, progress và reset thanh tiến trình. Ma trận đổi năm và giữ điều kiện của test suite cũ vẫn được chạy.
- QA Qt offscreen: kiểm tra ảnh trạng thái thành công/lỗi ở cửa sổ thực tế khoảng 780×780 và 685×600; status xuống dòng đủ chiều cao. Ảnh giả lập nằm trong `.cache/gtgt-lookup-*.png`.
- Bộ test hiện có bao gồm parser/export/golden GTGT, identity/ownership, integrity, kho local, phiên đăng nhập và CAPTCHA. Không sửa công thức/mapping/chỉ tiêu thuế, không chỉnh nội dung XML thuế.

Toàn bộ kiểm thử dùng thư mục tạm và fixtures kiểm thử có sẵn; không đọc `.env`/vault để lấy credential, không tra cứu cổng thật, không dùng hoặc thay đổi kho hồ sơ thuế thực tế.

## 5. Công việc còn lại và giới hạn quyền

1. Đối chiếu phiên bản/hash EXE và log đã che dữ liệu của ca 128/128 để xác nhận nguyên nhân tại phiên người dùng; kiểm tra trên đúng bản chạy. Live nghiệp vụ: **NOT_RUN** theo yêu cầu không thử bằng dữ liệu thuế thực tế.
2. Đã build lại EXE local ngày 03/11/2026, xem mục 6. Bản phát hành online cũ chưa có thay đổi; không push/deploy/release.
3. Kế hoạch AUTH_SCHEMA_UNKNOWN, XML dẫn xuất từ ZIP/mở bằng ứng dụng mặc định, benchmark tải và concurrency còn tiếp tục riêng. Không sửa selector/auth khi chưa có response chứng minh; không bật tải HTTP song song khi chưa chứng minh session isolation.
4. Theo dõi lỗi cleanup WinError 145 của baseline nếu CI Windows tái diễn; không gộp lỗi môi trường này thành lỗi dữ liệu thuế.
5. Không có `rg` trong môi trường nên dùng `git grep`/PowerShell. Liệt kê thư mục cha `C:\Users\dieut` bị từ chối quyền; không mở rộng quyền truy cập. Các file source và test cần thiết trong repo đều truy cập được.

## 6. Bổ sung ngày 03/11/2026 — cập nhật kho khi tác vụ đang chạy

- EXE trong `dist/` lúc bắt đầu vẫn là bản ngày 02/11, chưa chứa các sửa completion ở trên.
- Phát hiện thêm: UI chỉ đọc lại SQLite khi `len(pending_rows) % 100 == 0`. Lô nhỏ, lô cuối và các hồ sơ đã có không đảm bảo chạm điều kiện này; số Kho/Kỳ đang xem có thể giữ giá trị cũ giữa các lần đọc.
- Thay điều kiện số lượng bằng QTimer single-shot 250 ms: gộp các sự kiện progress rồi đọc các dòng đã commit. Áp dụng cho tax/GNT/thông báo và batch; dừng timer khi hoàn tất hoặc bắt đầu tác vụ mới. Khi đang tra cứu, view của thư mục cũ cũng chuyển về kho thuộc tài khoản hiện tại.
- Thêm ba regression: 128 hồ sơ mới cập nhật Kho/Kỳ ngay khi còn chạy; lô một hồ sơ cập nhật nhiều lần từ view thư mục cũ; completion hủy timer đang chờ và giữ trạng thái hoàn tất. Tổng regression: **16/16 PASS**.
- Build dùng worktree riêng `.cache/lookup-fix-buildsrc`, commit local `cf4167d248a51bf5fd3f1fb98963d1f088a76976`; giữ nguyên nhánh và index của workspace chính. Không push hoặc phát hành.
- Gate của source snapshot: **927 tests, 921 PASS, 6 skipped**, không lỗi; ruff PASS, mypy PASS (93 source files), dependency inventory PASS. Log: `.cache/lookup-fix-isolated-build-20261103.log`. Lượt gate ở workspace chính trước đó gặp lỗi cleanup Windows `WinError 145` trong test thông báo có sẵn; chạy riêng test đó lại PASS, và full gate trong worktree PASS.
- Vẫn chưa tái hiện phiên online cụ thể của người dùng hoặc thay đổi kho thuế thực tế.
- EXE mới: `dist/TaiHoSoThue-Windows.exe`, bản sao dễ phân biệt `dist/TaiHoSoThue-Windows-fix-tra-cuu.exe`; 90.420.310 bytes, SHA-256 `cf65239dc6f2da9701d692774dfbd8d33429193fdcf211a23f6cc4c7c9cbad9f`. Bản cũ được giữ tại `.cache/TaiHoSoThue-Windows-before-lookup-fix-20261103.exe`.
- Bundle audit PASS; source smoke và hai frozen smoke PASS, có SQLite/OCR/CAPTCHA fallback; native UI/DPI **18/18 PASS**. Evidence: `.cache/lookup-fix-buildsrc/.cache/smoke-bf7d1fab9fb64a8baf39276805b49c3d`; receipt/checksum tại `dist/release-manifest.json` và `dist/SHA256SUMS.txt`.
