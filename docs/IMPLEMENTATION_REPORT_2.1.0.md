# IMPLEMENTATION REPORT

Ngày: 02/11/2026. Phần source và kiểm thử offline đã hoàn thiện; chưa xác nhận full E2E với tài khoản thuế thật.

**Commit/base:** tiếp tục từ `59a41afee399dd23b9f13a832d97e2554fe79e84`; source build `07fcfd3d10929f54d80b78e7b56b10ab7c21f8f9`. Base trước toàn bộ nâng cấp: `ca4b220a455153941a5a1cead69e96d8622be4ea`.

**Branch:** `feature/persistent-catalog-smart-sync`. Chỉ commit cục bộ, chưa push/publish. Commit bàn giao tài liệu có thể nằm sau source build; hash trong EXE/manifest xác định source đã kiểm thử.

**Files changed:** lượt tiếp tục hoàn thiện `desktop/{jobs,migration,services,v2_interactions,v2_layout}.py`, `gdt_tax/{local_catalog,orchestration}.py`, `scripts/capture_v2.py`, `tests/{test_desktop_upgrade,test_local_catalog}.py`, README, metadata build và tài liệu tiến độ/migration/performance/release. Các phần SQLite/UI cốt lõi đã có trong base tiếp tục.

**DB location/schema:** schema v1, `ROOT/<account-namespace>/{to-khai,gnt,thong-bao}/catalog.sqlite3`; nhánh `tai-moi` được giữ khi workspace cũ chưa có owner. DB ngoài EXE, khóa account + mode + RecordKey; có FK, index ngày, quarantine, migration_sources và sync_runs. Không xóa inventory khi đổi kỳ hay online trả lỗi/rỗng.

**Migration result (dry-run/real):** fixture dry-run thêm 2, real thêm 2, lần sau ALREADY_IMPORTED; SHA-256 JSON/ZIP nguồn không đổi, integrity=ok. [Bằng chứng fixture](PERSISTENT_MIGRATION_EVIDENCE.json). Test import có owner, copy evidence/attachment và từ chối folder unowned đạt. Bổ sung preflight cả tệp chính/evidence trước copy: evidence đích xung đột thì không chép tệp chính hoặc ghi đè dữ liệu đích. Chưa migrate kho thuế thật.

**UI fix evidence:** không có nút “Sửa điều kiện”; bộ chọn kỳ, Từ/Đến và hai nút tra cứu luôn hiện. Regression 3 nghiệp vụ × 2 thao tác × 4 trạng thái SUCCESS/PARTIAL/ERROR/CANCELLED giữ nguyên ngày/preset. Job về muộn không kéo kỳ đang xem về kỳ cũ. Script capture chạy 6 cấu hình kích thước/scale, cả 4 tab và drawer GNT: PASS; đã kiểm tra ảnh có dữ liệu và các ô ngày. Import/verify/export local không bị ghi nhãn Online.

**Multi-year persistence evidence:** test chuyển 2025↔2026, restart, tách tài khoản và nhóm ngày chưa rõ: PASS, đổi kỳ không gọi HTTP. Source smoke và hai frozen smoke đều persistent_catalog=true.

**Dedup evidence:** 100 lần upsert × 100 records giữ 100 keys; thêm 5 giữ 105; tách source/tài khoản/lần nộp; SQLite integrity/FK regression PASS.

**Missing-download skip evidence:** pipeline mock 100 local/105 online, 98 tệp hợp lệ dùng lại, đúng 7 download calls; chạy lại 105 reused, 0 download calls. Registry file chính/attachment riêng; discovery/checkpoint không phụ thuộc xuất JSON/Excel thành công.

**Performance before/after (with numbers):** số đo đã có trên synthetic 100.000 metadata rows: median đọc/lọc JSON 600,132 ms, SELECT SQLite tương ứng 46,053 ms; 4.166 rows trong kỳ, 5 warm reads. Không chạy lại benchmark ở lượt tiếp tục và không suy thành tốc độ cổng thật. Bỏ xuất toàn danh mục ở các checkpoint desktop; chỉ xuất cuối lượt. [Phương pháp và số đo](PERFORMANCE_RESULTS.md).

**CAPTCHA tự động:** giữ nguyên GuiCaptchaSolver và các module OCR/portal so với base tiếp tục; thay đổi jobs.py chỉ ở nhánh import. Hai frozen smoke đều ocr_offline=true, captcha_fallback_bounded=true; OCR text/model/charset/CPU provider khớp source. Giữ 5 lần tự động rồi fallback nhập tay. Chưa xác nhận đăng nhập live ở lượt tiếp tục.

**Live test:** NOT_RUN nghiệp vụ; chưa có phiên đăng nhập do người dùng hoàn tất trong lượt này. Không đọc `.env`/credential thuế để tự chạy. [Báo cáo redacted](LIVE_TEST_RESULT_REDACTED.md).

**Unit/integration regression:** PASS, 911 tests chạy, 905 đạt và 6 skipped; 0 failures/errors, 63,402 giây. Ruff PASS; mypy PASS, 93 source files. Lệnh đầy đủ:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Python .venv-release/Scripts/python.exe -ToolsPython .venv-release-tools/Scripts/python.exe -SkipInstall
.venv-release/Scripts/python.exe scripts/capture_v2.py
```

**Windows EXE:** BUILT+SMOKE_PASS, Windows onefile Full/CPU OCR; bundle audit PASS, source/hai frozen smoke PASS, native UI/DPI **18/18 PASS**. Build command exit=0. Tệp `dist/TaiHoSoThue-Windows.exe`, 90.417.828 bytes; SHA-256 `f28572b62066aeb2e1451a8a1e51260498a4444908a678a3f68434d1d748e49a`. Checksum/receipt ở `dist/SHA256SUMS.txt` và `dist/release-manifest.json`. Log `.cache/persistent-resume-build.txt`; evidence `.cache/smoke-154b878ebd4f414f9d1eba47069f7651/`.

**Known limitations:** tải tuần tự; chưa bật worker 2/3 do chưa chứng minh session isolation/pilot live. Chưa chạy kho thật, Windows sạch/Windows 10 riêng hoặc SQLite đa máy/cloud-sync. Không coi mock/OCR offline là bằng chứng cổng đang cho đăng nhập. [Security review](LOCAL_DATABASE_SECURITY_REVIEW.md).

**Rollback steps:** đóng ứng dụng; sao lưu toàn workspace; giữ DB hiện tại rồi copy DB backup đã kiểm integrity thành `catalog.sqlite3`. File nguồn vẫn nguyên. EXE trước lượt tiếp tục được giữ tại `.cache/persistent-resume-backup/TaiHoSoThue-Windows-before.exe`; không xóa DB hoặc kho gốc. [Hướng dẫn chi tiết](LOCAL_DATABASE_GUIDE.md).
