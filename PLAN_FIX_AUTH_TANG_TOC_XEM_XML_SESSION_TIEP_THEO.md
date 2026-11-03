# Bàn giao session tiếp theo: lỗi AUTH, tăng tốc tải, xem XML trực tiếp

Ngày ghi: 02/11/2026. **Đây là nhận định và kế hoạch, chưa triển khai các thay đổi bên dưới.**

## 1. Yêu cầu người dùng — giữ nguyên phạm vi

1. Tăng tốc tải **tờ khai, thông báo thuế, giấy nộp tiền**, bằng giảm request vô ích, cải thiện xử lý local và/hoặc tải đồng thời có kiểm soát.
2. Với tờ khai, đổi thao tác **“Mở tệp” → “Xem file”**, mở **XML bằng ứng dụng mặc định của Windows**. Không bắt người dùng mở ZIP rồi giải nén thủ công. Không chuyển hành động này sang XML Viewer nội bộ.
3. ZIP tờ khai tải về cần tự giải nén lấy XML, giữ ZIP gốc và bằng chứng integrity. Hồ sơ đã tải trước nâng cấp cũng cần xem XML thuận tiện mà không tải lại ZIP hợp lệ.
4. Sửa lỗi người dùng vừa gặp: `AUTH_SCHEMA_UNKNOWN: Trang nghiệp vụ chưa được nhận diện; đã dừng xác thực lại.` Ảnh cho thấy `Online: 0 | Mới: 0 | Dùng lại: 0 | Lỗi: 1`.
5. **Không làm hỏng hoặc thay luồng CAPTCHA tự động đang dùng.** Giữ OCR, lựa chọn solver, tối đa 5 lần tự động rồi fallback nhập tay; không ép toàn ứng dụng sang manual.
6. **Chưa release bản mới.** Người dùng đã yêu cầu commit/push và merge main ở lượt trước, nhưng chưa cho phép phát hành. Lượt hiện tại chỉ yêu cầu ghi kế hoạch cho session sau; không tự triển khai/push/phát hành dựa vào file này khi chưa có yêu cầu tiếp tục.

## 2. Trạng thái đã hoàn thành để không làm lại

- Repo: `C:\Users\dieut\tai-ho-so-thue-gtgt`.
- HEAD khi ghi: `be65225847655c97224a91a3be33100809130883`; nhánh local `feature/persistent-catalog-smart-sync`. GitLab `origin/main` và nhánh feature đã được xác minh cùng commit này sau push. Remote GitHub tồn tại nhưng lượt trước chỉ push GitLab.
- Source build EXE: `07fcfd3d10929f54d80b78e7b56b10ab7c21f8f9`; commit sau chỉ metadata/tài liệu. Desktop 2.1.0, chưa tag/release.
- EXE local: `dist/TaiHoSoThue-Windows.exe`, SHA-256 `f28572b62066aeb2e1451a8a1e51260498a4444908a678a3f68434d1d748e49a`.
- Đã có SQLite inventory bền vững, local-first khi đổi kỳ, incremental upsert, skip file hợp lệ, import có ownership/backup/quarantine. **Không quay lại dùng rows của một job làm toàn bộ lịch sử.**
- Form ngày luôn hiện, không có “Sửa điều kiện”; không reset ngày sau tác vụ. Phải giữ hành vi này.
- Gate trước lượt này: 911 tests, 905 PASS/6 skipped; ruff/mypy PASS; source + 2 frozen smoke PASS, native DPI 18/18 PASS. Đây không phải bằng chứng đã sửa lỗi AUTH trong ảnh hoặc đã kiểm thử nghiệp vụ live đầy đủ.
- Xem thêm `docs/IMPLEMENTATION_REPORT_2.1.0.md`, `docs/IMPLEMENTATION_PROGRESS.md`, `docs/LOCAL_DATABASE_GUIDE.md`, `docs/PERFORMANCE_RESULTS.md` và kế hoạch gốc `PLAN_NANG_CAP_TAI_HO_SO_THUE_LOCAL_DATABASE_INCREMENTAL_SYNC.md`.
- Worktree main cũ tại `.cache/pr-worktrees/main-integration` có thay đổi metadata build chưa commit; **không reset/clean/ghi đè**. Dùng checkout/worktree sạch nếu cần. Không suy local main đã được cập nhật chỉ vì remote main đã cập nhật.

## 3. Nhận định lỗi AUTH — đã xác định gì, chưa xác định gì

### Bằng chứng source

- `desktop/sessions.py`, `ETaxSessionManager.execute()`: bắt `LegacyPageError`, trả thông báo chung giống hệt ảnh, `error_code='AUTH_SCHEMA_UNKNOWN'` và `errors=1`.
- `gdt_tax/errors.py`, `LegacyPageError`: trang legacy không có form/màn hình nghiệp vụ dự kiến sau đăng nhập; **không tự đồng nghĩa hết phiên**.
- Handler hiện bỏ chi tiết exception khi dựng `JobResult`; vì vậy ảnh không cho biết endpoint, giai đoạn navigation, form thiếu hay response cụ thể.
- `tests/test_sessions.py::test_page_open_failure_twice_reports_page_detail` hiện còn khẳng định chi tiết gốc KHÔNG nằm trong message. Khi cải thiện chẩn đoán cần sửa contract có chủ đích, vẫn redaction dữ liệu nhạy cảm.
- `gdt_tax/auth_outcomes.py` phân loại auth và `gdt_tax/portals/etax_legacy.py` có `LegacySessionNavigator`; GNT/TB dùng navigation legacy và session dùng chung.

### Giả thuyết cần kiểm chứng, không ghi thành nguyên nhân đã xác nhận

- Cổng đổi form/operation/navigation hoặc trả trang trung gian/redirect mà adapter chưa nhận diện.
- Session/token DSE còn tồn tại nhưng navigation state đã đổi khi chuyển giữa tờ khai/GNT/thông báo.
- Cổng trả trang bảo trì/xác minh truy cập hoặc hết phiên nhưng marker chưa được phân loại đủ.
- Chưa biết người dùng chạy tab nào, kỳ nào, bản EXE nào, và lỗi xuất hiện ngay sau login hay khi đổi nghiệp vụ. Các con số 0 trong ảnh không chứng minh online không có hồ sơ; lỗi xảy ra trước khi có kết quả xác nhận.

### Cách điều tra/sửa theo thứ tự

1. Đối chiếu phiên bản/hash EXE và log redacted của lần lỗi; xác định mode, stage, HTTP status, source và chuỗi navigation. Không đọc `.env`/vault để tự lấy credential, không yêu cầu dán password/cookie vào chat.
2. Giữ reason code/exception detail đã che bí mật trong issue/log: adapter, stage, tên form/operation dự kiến, status, fingerprint cấu trúc; không log query DSE/token, nội dung hồ sơ hay raw HTML vào repo/CI.
3. Đối chiếu `LegacySessionNavigator`, `desktop/sessions.py`, `gdt_tax/gnt/portal.py`, `gdt_tax/tb/portal.py`, classifier auth với response thật đã được cung cấp an toàn. Chỉ cập nhật selector/route khi có bằng chứng.
4. Phân biệt schema unknown, session expired, bảo trì và access verification. Chỉ reauth có giới hạn khi có bằng chứng hết phiên; schema unknown không được gây vòng login/CAPTCHA lặp.
5. Nếu chỉ thiếu navigation state, thử thiết lập lại luồng nghiệp vụ hợp lệ trong phiên hiện tại sau khi xác minh tính đúng đắn. Không mặc định đổi toàn bộ lỗi thành expired hoặc nới classifier nhận trang bất kỳ là login thành công.
6. Tạo fixture synthetic/sanitized và regression cho response gây lỗi. Kiểm chuyển tab tax→gnt→notice→tax, kỳ cắt legacy/DVC, reused session, expired session và unknown page. Lỗi phải giữ DB/file/local view, không hiển thị “không có hồ sơ” như kết quả thành công.

## 4. Tăng tốc — đo trước, giảm việc thừa trước đa luồng

### Hiện trạng liên quan

- `desktop/sessions.py` dùng khóa phiên; test hiện xác nhận tối đa một request active trên transport legacy. Không bỏ lock để chạy đồng thời một `requests.Session`/DSE state.
- `gdt_tax/http.py` đã giữ `requests.Session`/connection pooling. Không tạo lại kết nối/login cho từng file nếu phiên hiện tại còn hợp lệ.
- `desktop/settings_store.py`: mặc định `record_delay=0.25`, `page_delay=1.0`, `jitter=0.3`. Không đặt hết delay=0 để tuyên bố nhanh hơn; tổng thời gian còn do HTTP, retry và parsing/verification.
- Desktop đã giảm checkpoint JSON/XLSX: SQLite ghi tăng dần, export tương thích cuối lượt. Tệp hợp lệ đã được skip từ trước; benchmark phải phân biệt tối ưu mới với hành vi đã có.
- `gdt_tax/portals/dvc.py`: download chính/thông báo có `minimum_attempts=6`; retry thông báo dùng `retry_growth=1.3`. Audit request thực tế và `Retry-After`, không tăng số retry hoặc bỏ validate endpoint bắt buộc tùy tiện.
- Đọc trước `gdt_tax/traffic.py`, `http_policy.py`, `metrics.py`, `orchestration.py`, các pipeline tax/GNT/TB, `gdt_tax/portals/base.py`, DVC và `dvc_notices.py` để tìm detail/token đang được dùng lại ra sao; không giả định hiện chưa cache.

### Công việc đề xuất

1. Đo riêng từng nghiệp vụ: list/detail/validate/download/attachment/login/CAPTCHA/retry requests; wall time, wait time, p50/p95, bytes, parse/verify/DB/export time. Không chứa URL nhạy cảm trong metrics.
2. So cold download, warm download toàn bộ hợp lệ, và thiếu một phần. Đếm actual HTTP calls; warm download không được tải lại primary hoặc attachment đã hợp lệ.
3. Tìm detail fetch lặp giữa ZIP và attachments, truy vấn lại cùng trang, login lại vô ích, verify/hash toàn bộ kho trên UI, tìm record O(N²), ghi report lặp. Cache trong đúng account/session/task và TTL phù hợp; không reuse token một lần hoặc token đã đổi.
4. Điều tra chi phí `verify_rows` trên mỗi record/cache hit và lần verify cuối job; ưu tiên reuse kết quả verify còn hợp lệ trong job theo identity + size/mtime/evidence. Không giảm chuẩn integrity hoặc chỉ nhìn đuôi file.
5. Nếu network bị giới hạn bởi session: có thể song song hóa xử lý local độc lập như validate/giải nén/hash sau tải trong worker giới hạn, giữ HTTP tuần tự và tránh Qt UI freeze. Đo lợi ích CPU/I/O thực tế trước.
6. Chỉ thử HTTP download workers 2, tối đa 3, có feature flag và mặc định 1, sau khi chứng minh session/token/CSRF isolation của từng adapter. Không song song login/CAPTCHA. Trường hợp không chứng minh được thì giữ HTTP=1 và báo rõ giới hạn.
7. Shared rate limiter theo account+origin, bounded queue/backpressure, artifact lock, single writer SQLite, cancel/resume; fallback 1 hoặc dừng khi 429/503/403/access verification/session expiry. Không áp dụng quota ví dụ trong plan như quota chính thức của cổng.
8. Benchmark mock workers 1/2/3 (10/50/100 files), request count và data integrity; live mẫu nhỏ chỉ theo authorization/quota hiện có. Không stress cổng. Báo số đo thật, không hứa mức tăng tốc trước đo.

## 5. ZIP → XML và “Xem file” bằng ứng dụng mặc định

### Điểm sửa đã tìm thấy

- `desktop/table_model.py`: nhãn action đang là `Mở tệp` cho row downloaded.
- `desktop/v2_interactions.py`: `open_detail_file()` mở `_file_path`, hiện trỏ ZIP của tờ khai; nhãn drawer và menu phải cũng có “Mở tệp”. Audit thêm click cột action, double click và `desktop/ui.py` để hành vi thống nhất đúng scope tờ khai.
- `desktop/ui.py::open_path()` đã dùng `QDesktopServices.openUrl(QUrl.fromLocalFile(...))`, phù hợp mở ứng dụng Windows mặc định. Dùng lại cơ chế này cho đường dẫn XML.
- `desktop/file_store.py::DesktopZipStore` kế thừa `gdt_tax/storage.py::ZipStore`. `gdt_tax/storage.py` đã có decode/validate ZIP; audit `gdt_tax/integrity.py`/`atomic.py` trước khi thêm xử lý giải nén.

### Thiết kế cần triển khai

1. Giữ ZIP gốc, tên/path cũ, hash/evidence và identity hiện hữu. XML là derived artifact liên kết ZIP nguồn bằng hash + RecordKey; **không thay `tep_zip`/primary ZIP bằng đường dẫn XML**.
2. Sau ZIP hợp lệ, tự lấy XML vào thư mục riêng ổn định theo account/source/RecordKey. Chạy ngoài UI thread, lưu atomic, ghi registry/path sau khi thành công. Không lấy mỗi remote ID hoặc tên XML để gộp hồ sơ khác nguồn/lần nộp.
3. Không dùng `extractall` không kiểm tra. Chặn traversal/absolute/UNC/drive/symlink/path ngoài root, zip bomb, quá nhiều entry, quá lớn sau giải nén, file mã hóa/hỏng; chỉ xử lý XML cần thiết, giữ đủ các XML hợp lệ khi ZIP có nhiều tài liệu.
4. ZIP nhiều XML: xác định tờ khai chính dựa trên cấu trúc/nội dung đã có parser hỗ trợ; nếu mơ hồ, cho chọn danh sách XML có tên rõ. Không âm thầm mở XML chữ ký/phụ lục đầu tiên chỉ theo thứ tự ZIP.
5. “Xem file” ưu tiên XML chính đã kiểm tra, gọi ứng dụng mặc định. Nếu Windows chưa có ứng dụng mở XML, thông báo rõ và cho mở thư mục; không ép XML Viewer nội bộ, không tự đổi file association.
6. ZIP cũ hợp lệ: giải nén khi nâng cấp/nhấn “Xem file” lần đầu hoặc bằng job local giới hạn; không HTTP, không đổi byte ZIP, lần sau dùng lại derived XML nếu ZIP hash và manifest còn khớp. Không quét sâu toàn kho lúc đổi kỳ.
7. XML bị mất/hỏng hoặc ZIP thay đổi: tái tạo từ ZIP hợp lệ bằng thao tác local. Lỗi giải nén không được biến ZIP đã tải đúng thành “chưa tải” và gây tải lại vô ích. UI tách downloaded ZIP với trạng thái XML sẵn sàng/lỗi.
8. Giữ XML đúng byte gốc, không sửa nội dung/chữ ký. Xử lý file đang bị ứng dụng ngoài khóa, Unicode/path dài và cancel giữa chừng. Không mở file `.part`.
9. Phạm vi yêu cầu đổi mở bằng app mặc định là **tờ khai**. GNT thường đã XML và thông báo có PDF/XML/ZIP: audit để tăng tốc chung nhưng không tự thay toàn bộ viewer/phản hồi CQT ngoài yêu cầu.

## 6. Thứ tự session sau và tiêu chí nghiệm thu

1. Audit HEAD/status, đọc file này và kế hoạch gốc. Tái hiện/chẩn đoán AUTH trước; xác nhận app/adapter nào bị lỗi, giữ CAPTCHA tự động.
2. Sửa AUTH có fixture regression, bảo toàn dữ liệu và auth classification. Chưa có response tái hiện thì báo chưa xác định, không nhận là đã sửa root cause chỉ nhờ đổi message.
3. Thêm derived XML + “Xem file”; kiểm ZIP cũ/mới, nhiều XML, archive độc hại, file thiếu/hỏng, khác account/source cùng ID, mở Windows app, cancel/restart và zero HTTP khi xem local.
4. Đo baseline từng loại tải, triển khai giảm request/local work; chỉ thêm concurrency khi gate đạt. Mock 100→105, 98 reused/7 missing vẫn phải đúng; chạy lại 0 download calls cho file hợp lệ.
5. Full regression với environment `.venv-release`, ruff/mypy bằng `.venv-release-tools`; source/frozen OCR model/text/charset/provider và fallback 5 lần phải khớp. Kiểm login dùng lại giữa nghiệp vụ không sinh vòng CAPTCHA mới.
6. Giữ ngày/preset sau success/partial/error/cancel, local-first, zero duplicate, SQLite integrity/FK, ownership và rollback. Test cả legacy/DVC, tờ khai bổ sung, GNT, thông báo và attachment.
7. Báo cáo performance trước/sau có số request và wall time; live không chạy thì ghi NOT_RUN. Build EXE sau source chốt, smoke trên EXE đúng commit, cập nhật progress/report.
8. Chỉ commit/push/merge khi session tiếp theo được người dùng yêu cầu làm tiếp với phạm vi tương ứng. **Không tag/release/publish** nếu chưa có chỉ đạo mới rõ ràng.

## 7. Ghi chú bàn giao lượt lập kế hoạch

- Chỉ đọc source và ghi tài liệu này; không sửa runtime/CAPTCHA, không chạy online, không tạo build mới hoặc công bố bản mới.
- Không cần chạy lại test runtime cho thay đổi chỉ có tài liệu. Các gate nêu ở mục 2 là kết quả lượt trước, không phải bằng chứng cho yêu cầu mới.
- Ảnh lỗi gốc là ảnh người dùng gửi trong hội thoại; đã chép nguyên văn thông báo cần xử lý ở mục 1, không đưa ảnh/log thuế thật vào repository.
