# Mốc tiếp tục sửa core — 20/10/2026

Người dùng đã chốt **sửa toàn bộ 26 mục, chia nhiều PR/MR, commit và tạo MR**.
Ngày 20/10 người dùng yêu cầu lưu tiến trình để tiếp tục ở phiên sau.
**Chưa hoàn thành cả 26 mục. Chưa merge, build lại EXE hay thay release trong đợt này.**

## Mở đúng checkout

- Repo gốc: `C:/Users/dieut/tai-ho-so-thue-gtgt`.
- Checkout đang sửa: `C:/Users/dieut/tai-ho-so-thue-gtgt/.cache/pr-worktrees/core-review`.
- Nhánh hiện tại: `codex/core-inventory-profiles`, kế thừa MR !7.
- Baseline main: `559892f1ff22f3e68d2fbea7be0608fd0ac597c9`.
- Repo gốc có thay đổi UI/DVC và prompt cá nhân chưa commit: **không reset, clean,
  stash hay gom những thay đổi đó vào nhánh sửa core**. Tiếp tục trong checkout trên.
- Git metadata của worktree dùng chung repo gốc. Git mutation/push/API có thể cần
  escalation do sandbox. Người dùng đã cho phép commit/push/tạo MR; không hỏi lại
  phạm vi 26 mục. Không dùng tài khoản thuế, không đăng nhập thật để chạy test.

## Các MR đã tạo

| MR | Nhánh và commit | Target | Phạm vi |
| --- | --- | --- | --- |
| [!4](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/4) | `codex/core-review-20261020` / `c4d63d30973e06909dda0c2378452e9525b6ec60` | `main` | Báo cáo và 26 đầu việc, không đổi runtime |
| [!5](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/5) | `codex/core-xml-policy` / `d83a842332b8fb4b7862916ca19723d78fc5a561` | `main` | XML URI/scoping, giới hạn parser/inventory |
| [!6](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/6) | `codex/core-mapping-numbers` / `4179604289bd4aa645d17ec244d875e60318f7c2` | `codex/core-xml-policy` | Numeric formats, registry validation/compatibility |
| [!7](https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/merge_requests/7) | `codex/core-offline-reports` / `1f1b70207ae5adb10c0066af7d47ea1429bda1ff` | `codex/core-mapping-numbers` | Lineage, spreadsheet text/numbers, exit quality và audit |

Các MR runtime nối tiếp !5 → !6 → !7; !4 độc lập. Chưa kiểm tra trạng thái pipeline
GitLab hoặc mergeability sau khi tạo: phiên sau cần kiểm tra bằng API, sửa nếu lỗi.

MR !7 đã chạy **514 test: 508 đạt, 6 optional skip**; Ruff và mypy 70 module đạt.
Log: `.cache/optimization/pr-offline-final-tests.log` ở repo gốc. Helper ghi log
ban đầu lỗi decode ở bước đọc log; test subprocess trong log đã kết thúc OK.
Helper đã sửa `errors='replace'`, không phải lỗi test.

## Trạng thái 26 mục

`MR` nghĩa là đã triển khai trong MR, chưa merge; không phải mọi mục đã hoàn tất.

| ID | Trạng thái và việc còn lại |
| --- | --- |
| CORE-01 | Chưa làm: census, empty thật so với schema drift, mọi portal/pipeline |
| CORE-02 | Chưa làm: đọc cột theo tên/hợp đồng, phát hiện thiếu/đổi thứ tự |
| CORE-03 | Chưa làm: identity account/source/kind, catalog/resume/target/GUI migration |
| CORE-04 | MR !7: schema/count/lineage/source/hash/coverage và strict export |
| CORE-05 | MR !7: common literal XLSX text + safe CSV mọi writer hiện có |
| CORE-06 | MR !7: typed numeric cells, 15-digit/range fallback/warnings, raw text |
| CORE-07 | Parser trong !5/!6; inventory metadata scoping đang ở checkpoint, cần test mới |
| CORE-08 | MR !6: xml_decimal/vi/en/auto, ambiguous/malformed explicit warnings |
| CORE-09 | MR !6: strict registry schema, duplicate/version/date/namespace policy |
| CORE-10 | Draft hiện tại: cache bind root/profile/policy, copy cache, bounded raw read; chưa đủ test/hoàn thiện |
| CORE-11 | MR !7: 4 offline CLI exit 0/1/2 và optional quality JSON; online vốn có 0/1/2 |
| CORE-12 | !5 parser/inventory shared limits; còn download GNT/XML validators |
| CORE-13 | Chưa làm: XML kind, PDF integrity, reuse validation; DVC attachments WIP |
| CORE-14 | Chưa làm: HTTPS/origin/form/operation/redirect policy |
| CORE-15 | Chưa làm: bounded streaming/deadlines/retry budget; Retry-After inf |
| CORE-16 | Chưa làm: structured string/URL/Referer redaction, private/support dump, crash log |
| CORE-17 | !7 offline error/warnings/mapping/hash audit; còn attachment quality/counters |
| CORE-18 | Chưa làm: catalog checkpoint/performance/concurrent writers/atomic recovery |
| CORE-19 | Chưa làm: typed auth/session outcomes, maintenance khác captcha/credentials |
| CORE-20 | Chưa làm: versioned portal capabilities/routing plans |
| CORE-21 | Chưa làm: Protocol/Result, shared orchestration/session navigator; chia nhỏ |
| CORE-22 | Chưa làm: fixture provenance + contract/metamorphic tests đầy đủ |
| CORE-23 | Chưa làm: minimal/Windows/OCR CI, deps/build/source/version provenance |
| CORE-24 | Chưa làm: safe health/doctor và runbook khi cổng thay đổi |
| CORE-25 | Chưa làm: release replacement preflight/verify tất cả assets/rollback, mock only |
| CORE-26 | Draft hiện tại: structural roles, raw acceptance UNKNOWN; còn coverage/export/tests |

Chi tiết đầy đủ và acceptance của từng mục nằm trong MR !4:
`docs/core-review-20261020/{REPORT.md,TASKS.md,BACKLOG.json}`. Repo gốc cũng có
bản các file này chưa tracked. Đừng coi bản rút gọn ở đây thay thế acceptance.

## Draft hiện tại: tiếp tục từ đây

Checkpoint chỉ thay `gdt_tax/inventory.py`, `gdt_tax/classify.py` và tài liệu này.
**Chưa mở MR cho draft** vì chưa đủ acceptance; giữ local branch để hoàn thiện.

Đã thêm sơ bộ:

- `PROFILE_VERSION=xml-profile-v4`, cache policy digest và `InventoryCache` bind
  source root; cache schema/profile/limits đổi sẽ invalidate. Cache hit deepcopy
  để không mutate manifest cũ. Plain dict cache không được coi là có provenance.
- Raw files đọc với trần bytes; metadata filename trùng nhiều case không chọn bừa.
- Inventory metadata dùng `main_scope`, lọc namespace và phụ lục; giữ full skeleton.
- Profile thêm `document_root`, `structural_markers` để nhận diện role.
- Classifier v2 thêm cấu trúc appendix/notice conflict và invalid-profile conflict.
- File integrity tách riêng; acceptance luôn UNKNOWN, giữ raw status và source metadata.
- Discovery không xem chuỗi “chấp nhận” trong metadata là legal acceptance evidence.

Đã chạy sau các sửa draft: **17 inventory test + 5 classify test đạt**, mypy đạt.
Ruff chỉ báo import order; đã sửa trước checkpoint (xem kiểm tra thực tế khi tiếp tục).
**Chưa chạy full suite cho draft, chưa có test mới cho CORE-10/26.**

Việc kế tiếp:

1. Review lại draft, thêm regression cache khác root nhưng cùng path/size/mtime,
   profile/policy invalidation, rehash/cache mutation, raw read giới hạn, symlink và
   lỗi stat/read/hash (hiện một số I/O còn ở ngoài try). Test không giả vờ cache stat
   phát hiện được nội dung đổi nhưng giữ nguyên size/mtime; `--rehash` vẫn cần.
2. Test namespace/appendix/wrapper và skeleton không mất thông tin. Xem lại namespace
   signature cho wrapper; `default_ns` hiện root wrapper trong signature basis.
3. Hoàn thiện CORE-26: synthetic/anonymized fixtures có provenance cho declaration,
   appendix, notice, unknown, conflict; mapping coverage theo form/version/namespace,
   số chỉ tiêu có/thiếu. Export riêng parse quality, integrity, acceptance/raw/source.
   Không suy đoán nghĩa ctXX, không tự chấp nhận pháp lý, không ẩn lần nộp cũ.
4. Chạy targeted + full suite + Ruff/mypy/diff check, viết migration/policy docs,
   commit tiếp trên nhánh hiện tại, push và mở MR target `codex/core-offline-reports`.
5. Tiếp tục các mục còn lại theo dependency; đặc biệt CORE-21 là refactor lớn cần
   nhiều MR nhỏ sau typed contracts. Không đóng cả 26 chỉ vì đã có vài MR nền tảng.

## Công cụ và lệnh kiểm tra

Chạy trong checkout `.../.cache/pr-worktrees/core-review`:

```powershell
C:/Users/dieut/tai-ho-so-thue-gtgt/.venv-release-1.1/Scripts/python.exe -m unittest discover -s tests -q
C:/Users/dieut/tai-ho-so-thue-gtgt/.venv-review/Scripts/python.exe -m ruff check --no-respect-gitignore .
C:/Users/dieut/tai-ho-so-thue-gtgt/.venv-review/Scripts/python.exe -m mypy gdt_tax
git diff --check
```

Ruff cần `--no-respect-gitignore` vì checkout nằm trong `.cache`.
Helper full suite ghi log, chạy từ repo gốc:
`.venv-release-1.1/Scripts/python.exe .cache/optimization/check_core.py TEN_MOC`.

Helper GitLab private ở repo gốc `.cache/optimization/open_core_mr.py`; dùng
`--source codex/core-... --target codex/core-... --title ... --body-file PATH
--core-ids CORE-xx,...`. Nội dung MR là UTF-8 file thật. Credential đọc trong bộ nhớ
từ Windows CredentialManager qua `scripts/release_gitlab.py`; không ghi/in token.
Ledger MR: `.cache/optimization/core-mrs-created.json`.
Ledger task: `.cache/optimization/core-pr-progress.json`.

Snapshot WIP DVC lúc review:
`.cache/optimization/core-review-worktree-snapshot` ở repo gốc. Có
`gdt_tax/dvc_notices.py` và test chưa có trong main baseline. Khi sửa CORE-13/17/16,
đọc WORKTREE_ADDENDUM/WORKTREE_EVIDENCE và snapshot; đừng chép cả UI WIP vào PR.
Phụ lục cho thấy payload XML khai báo nhưng chứa HTML vẫn qua, reuse 1 byte,
lookup notice thiếu source, attachment lỗi không làm parent partial và crash log
chưa redact. Những lỗi này **chưa được sửa trong các MR đã mở**.

Không dùng lại các script one-time `.cache/optimization/edit_offline.py` hoặc
`edit_outcomes.py`; migration đã áp dụng. Không phát hành thật khi làm CORE-25.
