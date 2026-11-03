# Tiến độ nâng cấp 2.1.0

| Phase | Trạng thái | Triển khai / kiểm chứng |
|---|---|---|
| 00 | DONE | Audit base/version/dirty files, 887 tests baseline PASS; backup metadata/EXE cũ; fixture migration checksum; BASELINE_AUDIT.md |
| 01 | DONE | Bỏ nút và summary thu gọn; giữ form, preset/ngày; test job về muộn không kéo UI về kỳ cũ; đang chạy vẫn đổi ngày local được |
| 02 | DONE | gdt_tax/local_catalog.py, schema v1, FK/index, transaction riêng từng operation/thread, busy timeout 5s, quarantine, sync_runs, backup, inspector read-only; 100 upsert × 100 rows không trùng |
| 03 | DONE trên fixture | Import JSON có owner + RecordKey; dry-run trên DB bản sao; import idempotent, SHA file cũ không đổi. Explicit copy đã kiểm thử cả file chính/evidence/attachment; folder unowned chỉ xem. Chưa migrate kho thuế thật |
| 04 | DONE trên mock | SELECT SQLite theo ngày nộp/lập/gửi; nhóm ngày chưa rõ; counts kho/kỳ riêng; ngày theo fingerprint+mode; đọc local offline; đổi nơi lưu không xóa kho |
| 05 | DONE trên mock | Checkpoint trước/sau download; 100→105 giữ 105 keys; 98 valid reused, 7 download calls, chạy lại 0 download calls; cancellation giữ discovery; file + attachment registry riêng |
| 06 | DONE trên synthetic | Benchmark 100/1k/10k/100k; safe HTTP metrics; có test request reuse; không suy diễn tốc độ cổng thật từ benchmark local |
| 07 | BLOCKED với workers>1 | Giữ đường tải tuần tự hiện hữu. Chưa chứng minh session DSE/CSRF độc lập hay có pilot cho concurrent download; không mở worker 2/3. Đây là giới hạn có chủ đích theo gate của kế hoạch |
| 08 | PARTIAL / NOT_RUN nghiệp vụ | Pilot trước có login CANCELLED sau 6 requests, không discovery/download. Lượt tiếp tục chỉ chạy mock/offline/frozen, chưa có phiên live do người dùng hoàn tất. LIVE_TEST_RESULT_REDACTED.md ghi từng hạng mục chưa chạy; không xác nhận live PASS |
| 09 | DONE kiểm thử offline/build; live còn NOT_RUN | Source 07fcfd3: 911 tests OK (905 PASS, 6 skips), ruff/mypy PASS; onefile 2.1.0, bundle audit, source + hai frozen smoke SQLite/OCR PASS; native DPI 18/18 PASS. Capture fixture 6/6 PASS; regression giữ form/ngày 3 nghiệp vụ × 2 thao tác × 4 trạng thái. Giữ nguyên CAPTCHA tự động. Chưa push/publish; chi tiết/hash trong IMPLEMENTATION_REPORT_2.1.0.md |

File chính: desktop/{library,services,documents,jobs,state,ui,v2_layout,v2_interactions,main,live_pilot,smoke}.py; gdt_tax/{local_catalog,metrics,run_hooks,orchestration,http,ownership}.py; tests/test_local_catalog.py và regression contracts; scripts/{inspect_local_catalog,benchmark_local_catalog,smoke_test_windows}.

Dữ liệu bị ảnh hưởng: chỉ synthetic fixtures/temporary workspaces trong kiểm thử. Khi sử dụng app, SQLite nằm ngay trong thư mục nghiệp vụ đã có owner; JSON cũ được giữ, tệp gốc không bị migrate/đổi tên. Mọi phase có rollback trong LOCAL_DATABASE_GUIDE.md.

Lượt tiếp tục 02/11/2026: hoàn thiện import có owner/evidence/attachment, preflight xung đột trước copy; export cuối lượt, không ghi JSON/Excel toàn bộ ở mỗi checkpoint desktop. Sửa capture script theo local inventory/owner và ngày fixture thực tế; không đổi bộ giải CAPTCHA hoặc portal. Không can thiệp dữ liệu người dùng, chưa chạy live nghiệp vụ. EXE trước lượt tiếp tục lưu tại `.cache/persistent-resume-backup/`.
