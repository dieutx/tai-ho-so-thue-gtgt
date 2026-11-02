# MASTER PLAN & CODING AGENT PROMPT
## Nâng cấp Tải Hồ Sơ Thuế: Database bền vững, đổi kỳ không mất dữ liệu, đồng bộ bổ sung và tải nhanh có kiểm soát

**Repository:** https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/  
**Ứng dụng hiện tại:** Windows EXE v2.0.2 (theo màn hình người dùng)  
**Ngày lập yêu cầu:** 02/11/2026  
**Mục đích:** Giao trực tiếp file này cho Cursor / Codex / Claude Code / coding agent đang mở đúng thư mục clone của repository.  
**Kết quả yêu cầu:** Sửa source, chạy test, benchmark, kiểm thử một tài khoản thuế thật ĐƯỢC CHỦ TÀI KHOẢN CẤP QUYỀN, build EXE trên Windows và bàn giao báo cáo thực tế.  
**Trạng thái tài liệu:** Kế hoạch và yêu cầu triển khai; **chưa phải xác nhận tính năng đã được lập trình/test**.

---

# A. MASTER PROMPT — ĐỌC ĐẦU TIÊN

Bạn là **Principal Python Desktop Engineer + SQLite/Data Integrity Engineer + Performance Engineer + QA Lead**. Hãy nâng cấp trực tiếp repository `dieutx/tai-ho-so-thue-gtgt`, **KHÔNG** chỉ tư vấn, không tạo ứng dụng mới, không tự tuyên bố PASS nếu chưa chạy kiểm thử.

## A1. 6 yêu cầu không được thương lượng

1. **GIỮ NGUYÊN VÙNG CHỌN KỲ/NGÀY.** Sau khi bấm **Tra cứu** hoặc **Tra cứu và tải** và hoàn tất, tuyệt đối không thu gọn form thành dòng **“Sửa điều kiện”**. Không thêm nút “Sửa điều kiện” để bắt người dùng mở lại. Bộ chọn kỳ, **Từ**, **Đến** và nút tra cứu **luôn hiển thị** ở giao diện trực tuyến. Sau khi tải xong, ngày người dùng đã chọn **không tự đổi hoặc reset**. Có thể đổi kỳ ngay trên giao diện.
2. **DỮ LIỆU LÀ TÀI SẢN TÍCH LŨY, KHÔNG PHẢI KẾT QUẢ TẠM MỘT LẦN TRA CỨU.** Mọi hồ sơ của các năm 2025, 2026... đã phát hiện hoặc tải được phải lưu bền vững trong **SQLite local database**, theo đúng tài khoản thuế + loại hồ sơ + định danh từ nguồn. Đổi kỳ chỉ thay **VIEW/FILTER**, **KHÔNG DELETE**, **KHÔNG REPLACE TOÀN BỘ**, **KHÔNG XÓA lịch sử**. Dữ liệu ở kỳ cũ vẫn còn khi quay lại, kể cả sau khi đóng/mở EXE và khi online thất bại.
3. **CHỌN KỲ LÀ HIỂN THỊ LOCAL NGAY, TRA CỨU LÀ ĐỐI SOÁT ONLINE.** Ví dụ đã có toàn bộ năm 2025 và 2026, chọn 01/10/2026–31/10/2026: ngay lập tức hiển thị hồ sơ tháng 10 có trong DB, không cần mạng. Bấm **Tra cứu** để hỏi cổng thuế xem có hồ sơ mới, cập nhật trạng thái/metadata, bổ sung vào DB. Bấm **Tra cứu và tải** thì sau khi đối chiếu chỉ tải những **file còn thiếu/chưa hợp lệ**. Một kỳ đã tải trước đó vẫn được tra cứu lại khi cần để phát hiện hồ sơ nộp mới/bổ sung; không được mặc nhiên coi “đã đồng bộ một lần” là vĩnh viễn đầy đủ.
4. **ZERO DUPLICATE; ZERO SILENT DATA LOSS.** Sử dụng khóa định danh nghiệp vụ ổn định đã có trong repo, upsert idempotent, không dùng ngày/kỳ/tên file để gộp. Giữ phân biệt cùng kỳ có lần nộp khác nhau, tờ khai bổ sung, nguồn DVC/legacy, GNT, thông báo và tài khoản khác nhau. Nếu phát hiện xung đột identity hoặc dữ liệu không rõ nguồn, **quarantine/review** thay vì xóa hoặc gán bừa. Bảo toàn ZIP/XML/PDF và thông báo đính kèm.
5. **TĂNG TỐC CÓ SỐ LIỆU VÀ AN TOÀN.** Đo baseline trước; loại bỏ request và parse trùng, tái dùng connection/session đúng cách, batching hợp lệ, download song song **giới hạn và có feature flag** chỉ sau khi chứng minh thread-safety/session isolation và tuân thủ chính sách cổng thuế. **Không flood server, không vượt giới hạn, không né CAPTCHA, không phá anti-bot, không brute-force.** So sánh thời gian thực và số request trước/sau. Ưu tiên giảm request thừa trước đa luồng.
6. **KIỂM THỬ CẢ MOCK LẪN 1 TÀI KHOẢN LIVE ĐƯỢC CẤP QUYỀN.** Người dùng sẽ cấu hình tài khoản hợp pháp qua giao diện/Windows Credential Manager hoặc cơ chế nhập bí mật an toàn. **Không nhận mật khẩu qua prompt/repo, không hardcode, không commit token/cookie, không đưa dữ liệu hồ sơ thuế thật vào fixture/CI/log.** Test live chỉ đọc/tra cứu/tải hồ sơ được phép, khối lượng nhỏ có giới hạn; không nộp, xóa, sửa hồ sơ trên cổng. Nếu không có quyền/môi trường/mật khẩu, đánh dấu `NOT_RUN (blocked)`; không được giả vờ đã chạy live.

**Nguyên tắc thiết kế:** `Database = full persistent inventory`; `date controls = query filter`; `online results = incremental upsert`; `file system = evidence/artifacts`; `UI = projection`; `download manager = skip valid, fetch missing`. Tuyệt đối không để `self.model.rows` / `self.result.rows` của một tác vụ là nguồn dữ liệu lịch sử duy nhất.

## A2. Cách thực thi

- Audit code **đúng commit/branch** trước khi sửa: ghi `git rev-parse HEAD`, phiên bản app, `git status`, ghi nhận test baseline.
- Thực hiện **PHASE 00 → PHASE 09** bên dưới, theo thứ tự; mỗi phase có deliverables, test, gate.
- Mỗi phase xong phải cập nhật `docs/IMPLEMENTATION_PROGRESS.md` gồm `DONE/PARTIAL/BLOCKED`, danh sách file, test PASS/FAIL/NOT_RUN, dữ liệu bị ảnh hưởng và bước tiếp theo. Có thể dùng commit riêng theo phase; không push nếu chưa được yêu cầu.
- Không dừng ở báo cáo phân tích. Sửa code thật, tạo migration và test thật. Chỉ đặt câu hỏi nếu gặp chặn thực tế liên quan quyền live hoặc yêu cầu bên ngoài không thể suy ra.
- Không đưa cam kết số phút triển khai hoặc mức tăng tốc khi chưa đo.
- Mọi thay đổi phải có kế hoạch rollback. Không xóa data người dùng để làm test/migration.

---

# B. THỰC TRẠNG REPO — ĐIỂM PHẢI AUDIT

Các đường dẫn sau được quan sát trên nhánh `main` công khai ngày 02/11/2026; **đối chiếu lại source/commit checkout thực tế, không tin mù quáng tài liệu**.

| Nhóm | File / hàm cần xem | Vấn đề cần xử lý |
|---|---|---|
| Thu gọn bộ chọn kỳ | `desktop/v2_interactions.py` — `collapse_conditions()`, `on_completed()` | Có luồng gọi `collapse_conditions(True)` sau SUCCESS/PARTIAL và hiện `condition_summary` với nút “Sửa điều kiện” |
| Nút “Sửa điều kiện” | `desktop/v2_layout.py` — `self.edit_conditions` | Gỡ nút/summary không còn dùng, luôn để vùng điều kiện hiển thị; giữ responsive |
| Đổi ngày nhưng không lọc local | `desktop/v2_interactions.py` — `dates_changed()`, `apply_preset()` | Có thông báo “Điều kiện đã đổi; danh sách vẫn thuộc kỳ đã tra cứu trước đó”; thay bằng load DB theo date filter |
| Xóa danh sách khi bắt đầu tác vụ | `desktop/ui.py` — `launch(clear=True)` | Đang `self.result=None; self.model.reset(..., [])` khi tra cứu; thay bằng giữ view local/hiển thị tiến độ |
| Thay bảng bằng result mới | `desktop/v2_interactions.py` — `on_completed()` | Có `self.model.reset(self.mode, selected.rows...)`; chuyển sang `UPSERT DB → SELECT DB WHERE current filter` |
| Dữ liệu UI chỉ trong RAM | `desktop/state.py` — `TabState`; `desktop/ui.py` — `_restore_tab_state()` | Filter/sort được lưu nhưng rows không lưu; DB đảm nhiệm lịch sử |
| Thư mục theo tài khoản | `desktop/state.py` — `job_output()` | Có `to-khai`, `gnt`, `thong-bao`, `tai-moi`; bảo toàn namespace/ownership |
| Catalog JSON sẵn có | `gdt_tax/storage.py` — `write_metadata()`; `gdt_tax/gnt/storage.py`; `gdt_tax/tb/storage.py` | Có merge trong catalog, nhưng catalog không đủ thay UI persistence; migration sang SQLite, tránh double-write lệch |
| Danh tính bản ghi | `gdt_tax/identity.py` — `RecordKey`, `account_fingerprint()` | Tái dùng đúng khóa; không gộp 2 lần nộp bằng kỳ tính thuế |
| Kiểm tra file | `desktop/documents.py`, `desktop/file_store.py`, `gdt_tax/integrity.py`, `gdt_tax/ownership.py` | Bảo toàn evidence, hash/validation và không tải lại file đã hợp lệ |
| Online jobs | `desktop/jobs.py`, `desktop/services.py`, `gdt_tax/pipeline.py`, `gdt_tax/gnt/pipeline.py`, `gdt_tax/tb/pipeline.py` | Tách discovery, incremental update, download, cancellation, queue, checkpoint |
| HTTP & policy | `gdt_tax/http.py`, `gdt_tax/http_policy.py`, `gdt_tax/traffic.py`, `gdt_tax/redaction.py` | Instrument request, timeout, retry, pacing, rate limit; không lộ bí mật |
| Cài đặt | `desktop/settings_store.py`, `desktop/account_store.py` | Lưu ngày/kỳ UI riêng; mật khẩu chỉ trong cơ chế bảo mật đang có |
| Build/Test | `BUILD_WINDOWS.md`, `scripts/build_windows.ps1`, `packaging/TaiHoSoThue.spec`, `tests/` | Test hồi quy và Windows onefile |

**Bằng chứng source tham khảo:**
- `desktop/v2_interactions.py`: https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/main/desktop/v2_interactions.py
- `desktop/ui.py`: https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/main/desktop/ui.py
- `desktop/v2_layout.py`: https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/main/desktop/v2_layout.py
- `desktop/state.py`: https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/main/desktop/state.py
- `gdt_tax/storage.py`: https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/main/gdt_tax/storage.py
- `gdt_tax/identity.py`: https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/blob/main/gdt_tax/identity.py

## B1. Kịch bản nghiệp vụ chuẩn cần giữ nguyên

**Ví dụ 1 — Tích lũy nhiều năm**

- Đồng bộ/tải năm **2025**: DB chứa 1.500 hồ sơ ví dụ.
- Đồng bộ/tải 01–09/2026: DB thêm 900 hồ sơ, **tổng 2.400** (số minh họa, không phải dữ liệu thật).
- Chọn **tháng 10/2026**: bảng hiện các hồ sơ tháng 10 vốn có trong DB, hoặc trống **chỉ vì tháng 10 chưa có dữ liệu**, không vì 2.400 hồ sơ bị xóa.
- Bấm **Tra cứu** tháng 10: bổ sung metadata phát hiện mới. Bấm **Tra cứu và tải**: bổ sung file còn thiếu.
- Quay về năm 2025: đầy đủ 1.500 hồ sơ đã lưu; năm 2026 vẫn còn. Đóng EXE/mở lại cũng như vậy.

**Ví dụ 2 — Đồng bộ lại kỳ cũ**

- Đã có 100 hồ sơ tháng 10/2026, trong đó 98 file hợp lệ và 2 file còn thiếu.
- Cổng thuế hiện trả 105 hồ sơ, 100 cũ + 5 mới.
- Sau Tra cứu: DB có **105 khóa hồ sơ tháng 10**, không tạo 100 dòng trùng; 5 dòng mới có trạng thái chưa tải.
- Sau Tra cứu và tải: chỉ tải **2 file thiếu + 5 file mới** nếu còn thiếu tại thời điểm chạy; 98 file hợp lệ được dùng lại. Nếu một hồ sơ có thông báo đính kèm còn thiếu thì xử lý riêng attachment, không coi chính ZIP chưa tải.
- Quay lại kỳ khác và quay về tháng 10 vẫn còn 105 hồ sơ.

**Ví dụ 3 — Không nhầm “không hiển thị” với “đã xóa”**

- Kho DB toàn tài khoản: 2.505 bản ghi.
- View theo tháng 10: 105 bản ghi.
- Thay sang tháng 9: 100 bản ghi.
- View quay lại tháng 10: 105 bản ghi.
- **Global inventory vẫn 2.505 xuyên suốt**; phải có phép thử trực tiếp DB chứng minh.

---

# C. KIẾN TRÚC ĐỀ XUẤT VÀ DATA CONTRACT

## C1. Source of truth

1. **SQLite catalog là nguồn chính cho lịch sử và UI** (tạo bằng thư viện chuẩn `sqlite3`, không bắt buộc ORM).
2. ZIP, XML, PDF, attachments thực tế lưu ngoài DB trong thư mục user đã chọn; DB chỉ ghi metadata, đường dẫn, evidence/status. Không nhét BLOB tài liệu vào DB nếu không có lý do được chứng minh.
3. Các JSON/CSV/XLSX cũ là dữ liệu **migration import một lần** hoặc **export khả dụng**; không để database và JSON song song sửa khác nhau thành hai nguồn chính. Nếu pipeline cũ vẫn bắt buộc ghi JSON, thiết kế một write-through/reconciliation rõ ràng với transaction, checkpoint; **không dùng thay đổi JSON sau mỗi query để ghi đè toàn bộ DB**.
4. DB ở **thư mục dữ liệu bền vững ngoài EXE và ngoài PyInstaller temp**, theo account-namespace đã được xác thực dưới root người dùng chọn, ví dụ `ROOT/<account-namespace>/catalog.sqlite3` (đường dẫn chính xác do agent thống nhất sau audit). DB không được mất khi cập nhật/thay EXE.
5. Đổi `Nơi lưu`: **không xóa DB/file cũ**. Chỉ mở workspace tương ứng; tùy chọn import hợp lệ từ workspace cũ qua thao tác tường minh, kèm ownership verification và dedup.
6. `account_fingerprint` và `RecordKey` hiện có là nền tảng định danh; chủ sở hữu dữ liệu phải được kiểm tra bằng cơ chế `ownership.py`, không dựa riêng trên tên folder.

## C2. Schema tối thiểu đề xuất (agent chỉnh theo domain thực tế)

```sql
-- Đây là contract mức thiết kế, agent phải hoàn chỉnh migration SQL và constraints.
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
  account_key TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('tax','gnt','notice')),
  record_key TEXT NOT NULL,
  source TEXT,
  remote_id TEXT,
  document_kind TEXT,
  date_basis TEXT,
  document_date TEXT,         -- ISO YYYY-MM-DD, ngày áp dụng lọc
  tax_period TEXT,           -- kỳ tính thuế để hiển thị, KHÔNG làm key
  display_title TEXT,
  cqt_status TEXT,
  raw_metadata_json TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_online_seen_at TEXT,
  PRIMARY KEY (account_key, mode, record_key)
);
CREATE INDEX IF NOT EXISTS ix_documents_period
  ON documents(account_key, mode, document_date);

CREATE TABLE IF NOT EXISTS artifacts (
  account_key TEXT NOT NULL,
  mode TEXT NOT NULL,
  record_key TEXT NOT NULL,
  artifact_role TEXT NOT NULL, -- primary/receipt/acceptance/rejection/attachment...
  artifact_key TEXT NOT NULL,  -- ID nguồn hoặc reference ổn định
  relative_path TEXT,
  byte_size INTEGER,
  sha256 TEXT,
  evidence_json TEXT,
  verification_state TEXT NOT NULL DEFAULT 'unknown',
  last_verified_at TEXT,
  PRIMARY KEY (account_key, mode, record_key, artifact_role, artifact_key),
  FOREIGN KEY(account_key, mode, record_key)
    REFERENCES documents(account_key, mode, record_key)
);

CREATE TABLE IF NOT EXISTS sync_runs (
  run_id TEXT PRIMARY KEY,
  account_key TEXT NOT NULL,
  mode TEXT NOT NULL,
  from_date TEXT NOT NULL,
  to_date TEXT NOT NULL,
  state TEXT NOT NULL,         -- running/complete/partial/failed/cancelled
  started_at TEXT NOT NULL,
  completed_at TEXT,
  discovered_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  reused_count INTEGER NOT NULL DEFAULT 0,
  downloaded_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  request_count INTEGER NOT NULL DEFAULT 0,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS migration_sources (
  source_fingerprint TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  records_added INTEGER NOT NULL,
  records_updated INTEGER NOT NULL,
  status TEXT NOT NULL
);
```

Agent phải:
- Xác định `source`, `document_kind`, `record_key` và thuộc tính theo từng mode từ object thật; đảm bảo constraint không tạo false merge.
- Dùng UTC timestamp cho event và ISO date cho lọc, hiển thị theo định dạng Việt Nam. Không nhầm ngày nộp với kỳ tính thuế.
- Có mã hóa/định danh version schema, `PRAGMA foreign_keys=ON`, `busy_timeout`, WAL nếu phù hợp hệ thống file; **WAL trên network share/OneDrive cần đánh giá**. Không khẳng định mọi file sync cloud đều an toàn; trường hợp có nguy cơ hãy cảnh báo/chọn local path.
- Database truy cập theo **single-writer queue hoặc rõ transaction ownership**; không để 3 download threads cùng ghi connection SQLite không an toàn.
- Bảo toàn metadata cũ khi online response thiếu fields; status CQT mới chỉ cập nhật theo dữ liệu xác thực.
- Tất cả thao tác query/upsert parameterized SQL.
- Chú ý rollback, database backup và kiểm tra `PRAGMA integrity_check`.
- Không hard-delete hồ sơ khi online trả zero hoặc thiếu một nguồn.

## C3. Luồng dữ liệu chuẩn

```text
Đăng nhập/chọn account (hoặc mở local theo cơ chế có quyền)
        │
        ▼
Kiểm tra account namespace & mở SQLite
        │
        ▼
SELECT documents WHERE account/mode/date filter → UI
        │
        ├── Đổi kỳ/ngày/tìm kiếm: chỉ SELECT DB (KHÔNG HTTP)
        │
        └── Bấm Tra cứu / Tra cứu và tải
                 │
                 ▼
        Online discovery (các trang & nguồn hợp lệ)
                 │
                 ▼
       Upsert DB theo stable RecordKey, không DELETE lịch sử
                 │
                 ▼
       Reload view đúng kỳ mà UI đang chọn (đã có + bổ sung)
                 │
                 └── Nếu Tra cứu và tải:
                        Verify existing artifacts → skip hợp lệ
                        Download missing/invalid (bounded)
                        Commit từng kết quả/checkpoint → refresh view
```

## C4. Phân biệt 3 phạm vi, tuyệt đối không nhập nhằng

- **Tổng kho:** toàn bộ bản ghi account+mode trong DB qua các năm.
- **Đang xem:** số bản ghi account+mode nằm trong kỳ/ngày/bộ lọc hiện tại.
- **Tác vụ đồng bộ vừa chạy:** server phát hiện bao nhiêu, bao nhiêu mới, cập nhật, tải mới, dùng lại, lỗi.

Một lần sync tháng 10 **không được làm tổng kho giảm** do bảng đang hiện riêng tháng 10. Bất kỳ code `.reset(selected.rows)` nào làm mất lịch sử ở memory phải được đặt sau SELECT DB theo filter; DB vẫn nguyên dù UI đổi view.

---

# D. ROADMAP TRIỂN KHAI CHIA PHASE

## PHASE 00 — Baseline, inventory & an toàn dữ liệu

**Mục tiêu:** Không sửa vội khi chưa có số liệu và backup.

**Tasks**
1. Checkout source đúng phiên bản, ghi commit và version/branch. Xem `AGENTS.md`, `CONTRIBUTING.md`, `SECURITY.md`, build/test rules nếu có.
2. Tạo nhánh `feature/persistent-catalog-smart-sync` (không force push).
3. Kiểm thử hiện tại: login mock, search, download, đóng/mở, đổi kỳ, đổi account, export, legacy migration.
4. Làm việc trên **bản sao** thư mục dữ liệu 2025–2026; snapshot nguyên trạng (manifest SHA-256 hoặc content inventory) trước mọi migration.
5. Lập biểu đồ đường đi record: portal → pipeline → JSON → `JobResult` → `TabState` → `RecordsModel` → UI. Chỉ ra nơi `model.reset` gây biến mất dữ liệu và nơi `collapse_conditions(True)` gây nút “Sửa điều kiện”.
6. Instrument HTTP metrics an toàn: request count theo endpoint category, attempts, 2xx/4xx/5xx, elapsed, retries, records/s, files/s, byte/s, cache hits. **Không log token, payload thuế hoặc URL có secrets**.
7. Chạy `pytest` baseline, ghi failures sẵn có và môi trường Windows/Python.

**Deliverables:** `docs/BASELINE_AUDIT.md`, backup + checksum/manifest, test baseline, danh sách code points cần sửa.

**Gate:** Chứng minh có backup và số baseline; không đụng file thật của user.

## PHASE 01 — Sửa UI: luôn hiện ngày, không có “Sửa điều kiện”

**Mục tiêu:** Sửa ngay lỗi trải nghiệm, độc lập với database.

**Tasks**
1. Trong `desktop/v2_interactions.py`, loại bỏ hành vi thu gọn điều kiện sau completion; sửa `collapse_conditions` hoặc loại bỏ chức năng theo đúng cơ chế layout.
2. Trong `desktop/v2_layout.py`, bỏ nút **“Sửa điều kiện”** và summary thay form; `config_panel` luôn hiển thị trong các tab online.
3. Giữ nguyên `preset`, `from_date`, `to_date` sau **Tra cứu**, **Tra cứu và tải**, **Tải chưa tải**, **Thử lại** và sau khi kết thúc/cancelled.
4. Khi user sửa ngày, không hiển thị thông điệp sai kiểu “danh sách vẫn thuộc kỳ đã tra cứu trước đó”; phase 04 sẽ nối ngay DB, trước đó phải có UI behavior có test không tự bật mạng.
5. Kiểm thử trên cửa sổ nhỏ 1075×700 và high DPI: không che nút **Tra cứu**, ngày `dd/MM/yyyy` không xuống dòng bất hợp lý; không làm sai các tab khác.
6. Không cho tác vụ đang chạy tự thay đổi kỳ đã được user chỉnh trong lúc job, kết quả job được ghi DB ở phase sau.

**Deliverables:** UI code + screenshot before/after + regression test.

**Gate:** Sau tải thành công, vẫn thấy nguyên bộ chọn kỳ và hai ngày; không còn “Sửa điều kiện”; ngày không reset.

## PHASE 02 — Thiết lập SQLite catalog & repository API

**Mục tiêu:** Tạo nguồn lịch sử bền vững, không phụ thuộc view.

**Tasks**
1. Viết module ví dụ `desktop/catalog_db.py` hoặc `gdt_tax/local_catalog.py`, giao diện rõ `initialize`, `upsert_documents`, `upsert_artifacts`, `get_documents(account,mode,from,to,filters)`, `get_counts`, `get_document`, `start_sync_run`, `finish_sync_run`.
2. Thiết kế schema C2 sau khi đối chiếu record thật, chỉ số index, version migrations, rollback.
3. Dùng `RecordKey` hiện hữu làm key; bảo đảm account scoping, mode/source/kind isolation.
4. Upsert không đè `_file_path`/`tep_zip`/attachment evidence bằng rỗng; không đè trạng thái CQT thành unknown nếu đã có thông tin xác thực mới hơn.
5. Viết ingestion per mode `tax`, `gnt`, `notice`, metadata normalization, date parse, ISO index.
6. `document_date` bị thiếu/invalid phải được lưu (không discard). Xếp vào nhóm **“Ngày chưa xác định”**, có thông tin để user rà soát; **không tự đưa vào một khoảng ngày chưa khớp**.
7. DB phải bảo toàn 2 bản ghi cùng kỳ nhưng khác mã hồ sơ/lần nộp. Với ID chưa đủ chứng cứ, không tự tổng hợp hoặc đoán.
8. Một file có nhiều định danh nghiệp vụ hợp lệ phải được mô hình hóa qua `artifacts` / mapping phù hợp, không dùng hash vật lý làm identity.
9. Đảm bảo transaction, single writer, retry bounded cho SQLITE_BUSY, atomic checkpoint.
10. Tests: upsert idempotency, multi-year, same-period supplemental, per-account isolation, crash recovery, SQL injection via fields, unicode Vietnamese.

**Deliverables:** DB module + schema migration + unit tests + database inspection script read-only.

**Gate:** Có thể import 100 records, upsert lại 100 lần không tăng count; thêm 5 count=105; đổi filter không làm DB mất record; `PRAGMA integrity_check` OK.

## PHASE 03 — Migration dữ liệu JSON/ZIP/XML/PDF 2025–2026

**Mục tiêu:** Nâng cấp mà KHÔNG mất hồ sơ đã tải từ v2.0.2 hoặc bản cũ hơn.

**Tasks**
1. Audit `desktop/migration.py`, `gdt_tax/migrate_identity.py`, `ownership.py`, các JSON `danh_sach_ho_so.json`, GNT, thông báo và các file evidence.
2. Thực hiện **dry-run migration** trên bản sao, in ra: nguồn, account, tổng rows, rows hợp lệ, thêm mới, trùng, xung đột, tệp tồn tại/hỏng/thiếu, bị quarantine.
3. Migrate JSON metadata vào SQLite theo `RecordKey`, không xóa JSON; file ZIP/XML/PDF vẫn ở chỗ cũ, DB trỏ bằng relative-path an toàn theo root nếu có thể.
4. Nếu JSON/DB metadata thiếu nhưng file có chứng cứ xác định ownership, hỗ trợ reconciliation; nếu không đủ bằng chứng, đưa vào hàng **Cần xác minh**, không import âm thầm vào nhầm tài khoản.
5. Gắn `migration_sources(source_fingerprint, ...)` để chạy lại không tạo trùng.
6. Có backup DB trước schema upgrade, rollback nếu integrity check fail; không chạy destructive migration trên folder thật khi chưa có backup.
7. Nếu `job_output` chọn `tai-moi` do legacy unowned, giữ nguyên policy. Không tự nhập hồ sơ chưa có owner chỉ vì có tên file giống MST.
8. Nạp thông báo đính kèm và các file đã tải từng phần: không bỏ qua attachment hỏng chỉ vì ZIP hợp lệ.
9. Compare manifest trước/sau: số file gốc, SHA-256 các file cũ không đổi; số record phân loại có giải thích được.

**Deliverables:** migration code + report dry-run + recovery/rollback guide + tests với fixture legacy.

**Gate:** 2025/2026 có đủ hồ sơ cũ trong DB; migration lại idempotent; không đổi byte file tải cũ.

## PHASE 04 — LOCAL-FIRST view, đổi kỳ và full-inventory không mất dữ liệu

**Mục tiêu:** Đây là phase hoàn tất hành vi quan trọng nhất mà người dùng yêu cầu.

**Tasks**
1. Sau login thành công (hoặc vào chế độ xem local có quyền, nếu hỗ trợ), mở SQLite đúng tài khoản và `SELECT` hồ sơ theo kỳ hiện tại; tuyệt đối không HTTP để nạp local.
2. Kết nối `dates_changed()` và `apply_preset()` với **date-filtered SELECT**; tránh trigger nhiều query UI khi set từ/đến liên tiếp (debounce hoặc batch signal control).
3. Gõ tìm kiếm và lọc status/CQT/loại chỉ thao tác local; có thể dùng SQLite FTS hoặc query index nếu benchmarking 10k–100k rows cần, không tự thêm FTS nếu chưa cần.
4. `launch(clear=True)` không xóa view local; đổi sang progress state overlay, giữ danh sách hiện có và key selection hợp lệ.
5. Trong `on_completed`, không gán `selected.rows` làm toàn bộ catalog. Upsert online result → SELECT database theo **đúng khoảng ngày đang thấy trên UI**; nếu user đổi kỳ khi job chạy, kết quả trả về vẫn lưu DB nhưng view không nhảy kỳ ngược.
6. Lọc ngày theo `ngay_nop` cho tờ khai, ngày lập cho GNT, ngày gửi cho thông báo (theo field thực tế được audit); không lấy `ky_tinh_thue` thay ngày nộp.
7. Giữ lựa chọn kỳ/ngày khi đổi tab, tái mở EXE. Chỉ lưu UI date/preset per account+mode không kèm mật khẩu. Không sửa preset người dùng nếu kết quả job về muộn.
8. Thêm count rõ: `Kho: X | Kỳ đang xem: Y | Đã tải: Z | Thiếu file: N`, và metrics của lần sync riêng; tránh lẫn `kỳ vừa tra cứu` với `kỳ UI đang chọn`.
9. Trạng thái “đã tải” dựa vào file evidence/verification thực; đừng báo xanh nếu file không tồn tại. Kiểm tra mỏng lúc read (stat/manifest) và deep verification theo yêu cầu/tác vụ, tránh hash 100k file khi chuyển kỳ.
10. Hành động **Tải chưa tải** trên local: chỉ cho tải khi có bằng chứng remote ID và phiên xác thực hợp lệ; nếu cần re-query để lấy URL/token hợp lệ, thực hiện đúng luồng online rõ ràng, không im lặng gửi request khi user chỉ lọc view.
11. Lỗi/cancelled/partial server phải giữ 100% DB và view local trước đó; row mới đã thành công vẫn được commit.
12. Offline: nếu login yêu cầu mạng và thất bại, có thể chọn **Xem hồ sơ đã lưu** qua lựa chọn account được xác nhận cục bộ, chỉ read-only, không tự nhận là đã login cổng thuế.

**Deliverables:** UI wiring + local query model + per-account preferences + integration tests.

**Gate bắt buộc:** Tải năm 2025, 2026 → đổi tháng 10/2026 → quay về 2025/2026 → tất cả vẫn còn; đóng EXE mở lại vẫn còn. **Đây là release blocker.**

## PHASE 05 — Smart Sync, tải bổ sung, resume và zero duplicate

**Mục tiêu:** Người dùng chọn kỳ cũ để biết thiếu hoặc có thêm gì, không mất dữ liệu đã có.

**Tasks**
1. Tách rành mạch `search_only`, `search_and_download`, `download_missing`, `verify`, `open_local`, `export`; audit tất cả code paths.
2. Khi **Tra cứu**: online pagination đầy đủ trong range → `UPSERT` từng batch → refresh DB view → report `found online`, `new`, `updated`, `unchanged`.
3. Khi **Tra cứu và tải**: discovery như trên, sau đó xây hàng đợi artifacts còn thiếu/hỏng; skip các file hợp lệ đã có, không gọi endpoint download thừa.
4. **Không lấy `0 hồ sơ` ở một query lỗi làm bằng chứng để xóa hồ sơ cũ.** Khi query hoàn tất hợp lệ mà không có bản ghi, DB cũ vẫn giữ và UI báo “Không có hồ sơ mới từ lượt tra cứu này”.
5. Persist checkpoint từng batch/record thành công. Tắt app giữa 1000 file → mở lại có thể resume những file chưa hoàn tất; không tải lại file đã hợp lệ.
6. Partial download: ghi `.part` vào vị trí an toàn, validate rồi rename atomic; không nhận file nửa chừng là đã tải; xử lý dọn file tạm stale một cách không phá hoại.
7. Tách trạng thái primary ZIP/XML/PDF khỏi receipt/notice attachments. “Đã tải tờ khai” không có nghĩa “đã đủ toàn bộ thông báo đính kèm”.
8. Lựa chọn tải hàng loạt phải dựa trên document IDs đúng kỳ hiện tại; bảo đảm selection không lẫn tài khoản/kỳ sau UI đổi.
9. Đảm bảo `verify`, `export`, `download_selected`, batch operation không vô tình ghi DB bằng list rút gọn hoặc thay hồ sơ các tab khác.
10. Ghi `sync_runs` có thời gian và mức hoàn tất. History chỉ là audit log, không phải nguồn rows.
11. Nếu server không thể chứng minh kết quả đầy đủ (pagination thiếu, timeout, một nguồn thất bại), đánh dấu `PARTIAL`; không hiển thị “đã đồng bộ toàn kỳ”.

**Deliverables:** smart-sync engine, artifact registry, checkpoint/retry, integration test.

**Gate:** Local 100 + online 105 → DB 105; file 98 có sẵn + 7 thiếu → chỉ tải 7 file cần thiết, số request download cho 98 file cũ = 0; không duplicate.

## PHASE 06 — Performance audit: giảm request vô ích TRƯỚC khi đa luồng

**Mục tiêu:** Tăng tốc có kiểm chứng; không phá điều kiện an toàn của cổng thuế.

**Tasks**
1. Dùng mock HTTP/replay sanitized và một live pilot có phép để đo baseline: tổng requests, req/record, request latency p50/p95, page count, retries, login/captcha occurrences, download MB/s, total elapsed, database time, UI render time.
2. Phân loại request: bắt buộc (login, list, download missing, details required) và có thể bỏ (download lại valid, fetch details lặp, query pagination trùng, login lại vô ích, verify remote khi local evidence đủ).
3. Tái dùng authenticated HTTP connection pooling **nếu code HTTP support và thread-safe**, không tái sử dụng context không an toàn.
4. Có dedup đối với request cùng document+resource đang chạy; prevent double click double query. Chỉ cache response immutable hợp lệ trong phạm vi auth và expiry an toàn.
5. Reuse danh sách đã parse giữa progress/UI/DB, không serialize-reparse JSON nhiều lượt; không lập lại index danh sách O(N²).
6. Batch DB transactions nhỏ; sử dụng `executemany`/upsert đúng cách; UI update theo batch (ví dụ 100–250 records) thay vì `model.reset` từng record nếu làm UI chậm, nhưng không trì hoãn commit thực tế quá lâu.
7. Có option điều chỉnh `PAGE_SIZE`/date chunk **chỉ trong giới hạn portal được hỗ trợ**; bảo đảm không bỏ trang, không miss record ở boundary, không tăng request vô ích.
8. Rate/timeout/retry policy: tối ưu bằng đo, không set delay về 0 tùy tiện; áp dụng backoff+jitter và `Retry-After` khi có.
9. Tối ưu file verify: hash lần tải đầu; lần mở view chỉ stat/lightweight; rehash khi metadata mâu thuẫn, đổi file, hoặc user bấm kiểm tra sâu.
10. Viết benchmark mock có thể tái chạy và baseline table của các chế độ 1x–N records.

**Deliverables:** `docs/PERFORMANCE_BASELINE.md`, `docs/PERFORMANCE_RESULTS.md`, tracing được redaction, test về request count.

**Gate:** Chứng minh số request thừa giảm hoặc bằng 0 cho valid cached files; không chỉ báo “nhanh hơn” bằng cảm giác. Không tăng tỷ lệ lỗi.

## PHASE 07 — Bounded concurrency (đa luồng tải) có feature flag

**Mục tiêu:** Tăng throughput khi server và loại endpoint cho phép.

**Tasks**
1. **Không song song hóa login/CAPTCHA hoặc discovery nếu chưa xác minh portal hợp lệ và không xung đột session.** Bắt đầu thử song song ở **download các file độc lập** sau khi lấy danh sách.
2. Đánh giá `requests.Session`, cookie, CSRF, token, one-time download URL, thread-safety. Nếu session không an toàn, dùng các session độc lập có cấu hình xác thực hợp lệ, hoặc giữ concurrency=1; không copy token sang session trái quy trình.
3. Giới thiệu setting **Tải đồng thời**: `Tự động` (mặc định thận trọng) / `1` / `2` / `3`. Bản an toàn mặc định **1** trước khi live pilot; chỉ tăng mặc định khi có bằng chứng server chấp nhận. Không mở số workers không giới hạn.
4. Tổng request rate cap **theo tài khoản + origin**, không phải mỗi worker riêng. Ưu tiên giới hạn thận trọng (ví dụ tối đa 1 yêu cầu/s tổng khi chưa có tài liệu cổng), sau pilot điều chỉnh thấp hơn nếu có dấu hiệu rate limit; **đừng coi mức ví dụ là quota chính thức**.
5. Global shared `StopToken`, task queue, single-writer DB; worker chỉ download/verify và gửi kết quả về writer/UI Qt signal.
6. Adaptive concurrency: khi 429/503, Retry-After, CAPTCHA/403/session expiry, tăng latency hay số lỗi cao → tự giảm xuống 1 / tạm dừng; không cố lặp để vượt chặn.
7. Giới hạn retry nhỏ, có exponential backoff+jitter; retry chỉ thao tác idempotent có chứng minh an toàn.
8. Bảo đảm tên file không race, không ghi đè khác identity, atomic final save, lock từng artifact. Không để 2 workers cùng download cùng 1 ID.
9. Cho phép hủy an toàn, resume; DB không bị corrupt khi Ctrl+C, đóng app, session expire.
10. Benchmark 1, 2, 3 workers trên mock tải file 10/50/100; trên live chỉ thử **mẫu nhỏ hợp lệ**, so request count/latency/error/throughput. Chỉ bật tùy chọn nhanh hơn nếu có lợi thực đo và tuân thủ portal.

**Deliverables:** bounded download executor, toggles, load tests, benchmark table, safe fallback.

**Gate:** Không mix account/session, không dữ liệu hỏng/trùng, không spam portal; concurrency>1 chỉ bật nếu live pilot có quyền xác nhận ổn định.

## PHASE 08 — E2E test với MỘT tài khoản thuế live được cấp quyền

**Mục tiêu:** Chứng minh tính năng trên dữ liệu thực tế có quyền truy cập, đồng thời bảo mật.

### Điều kiện tiên quyết

- Chủ tài khoản/chủ doanh nghiệp **đồng ý rõ** cho agent/người vận hành kiểm tra bằng tài khoản đó; môi trường triển khai có khả năng đăng nhập hợp pháp.
- Tài khoản được nhập **trực tiếp vào dialog ứng dụng hoặc Windows Credential Manager** của máy người vận hành. Không yêu cầu dán mật khẩu vào chat/coding prompt, không ghi `.env` committed.
- Agent có thể hướng dẫn người vận hành hoàn tất CAPTCHA thủ công nếu cổng yêu cầu; không làm công cụ phá/bypass cơ chế xác thực.
- Cung cấp `LIVE_TEST_ENABLED=1` **chỉ ở môi trường thử nghiệm được cho phép**, live test mặc định OFF trong test suite và CI.
- Chỉ chạy tác vụ **tra cứu và download**, không nộp/sửa/xóa dữ liệu thuế trên cổng.
- Giới hạn vòng đầu một khoảng ngày rất ngắn, số tài liệu và request có quota rõ trong `docs/LIVE_TEST_PROTOCOL.md`; nếu gặp 429/403/rate-limit, CAPTCHA bất thường, dừng ngay.
- Trước khi làm trên dữ liệu live, tạo backup và snapshot DB/files; không dùng tài khoản thật để phá hủy dữ liệu test.

### Test flow bắt buộc

**L1.** Đăng nhập đúng 1 tài khoản được phép, ghi nhận account fingerprint rút gọn ở local report (không ghi MST đầy đủ).  
**L2.** Chọn mẫu một khoảng ngắn năm 2025: `Tra cứu`, `Tra cứu và tải` với quota phù hợp; ghi số rows và file thực có.  
**L3.** Chọn mẫu năm 2026 hoặc tháng 10/2026; tải bổ sung; chụp số tổng kho trước/sau; tổng kho không giảm.  
**L4.** Quay lại kỳ 2025 và quay lại kỳ 2026; không có request HTTP trong quá trình **chỉ chuyển kỳ**; số lượng và đường dẫn file khớp.  
**L5.** Đóng EXE hoàn toàn → mở lại, đăng nhập lại/đọc local → các kỳ vẫn hiện và file mở được.  
**L6.** Tra cứu lại cùng kỳ: `new=0` nếu server không thay đổi; không sinh dòng trùng; khi `Tra cứu và tải` thì download request với file valid existing = 0.  
**L7.** Với sự cho phép và nếu thực tế có hồ sơ mới, thử phát hiện mới; nếu không có dữ liệu mới thật, dùng **mock server** để kiểm thử scenario `100→105`, **không chỉnh hồ sơ thuế thật để phục vụ test**.  
**L8.** Test offline local, hủy tác vụ an toàn, mất kết nối (mô phỏng); file cũ/DB vẫn nguyên.  
**L9.** Test GNT và Thông báo thuế với mẫu vừa đủ, đảm bảo phân tách nguồn và file đính kèm.  
**L10.** So benchmark serial vs 2 workers trên tập nhỏ **nếu server cho phép**, dừng khi dấu hiệu bất thường; không benchmark stress tải cổng thật.  
**L11.** Kiểm tra DB `integrity_check`, số orphan paths, fingerprint manifest, compare counts theo account/mode/date.  
**L12.** Xóa/ẩn toàn bộ bí mật và dữ liệu thuế trước khi chia sẻ report, screenshot, log hoặc fixtures.

### Báo cáo live bắt buộc

| Chỉ tiêu | Yêu cầu ghi |
|---|---|
| Account | fingerprint rút gọn, không lộ credential |
| Phạm vi | loại hồ sơ, khoảng ngày, số lượng tài liệu được phép |
| Date switching | thời gian select local, HTTP request count phải bằng **0** |
| Persistence | count kho trước/sau chuyển kỳ và sau restart |
| Dedup | số key duy nhất, conflicts, duplicate count |
| Download reuse | file valid reused, missing downloads, request count |
| Performance | baseline/optimized, workers=1/2 nếu có, p50/p95, errors |
| Reliability | status PASS/FAIL/NOT_RUN và log đã redacted |

**Nếu không có quyền truy cập live: không tiến hành; báo `BLOCKED/NOT_RUN`, hoàn thiện tất cả mock/integration tests và đưa checklist cho người dùng chạy trên máy của mình.**

**Deliverables:** `docs/LIVE_TEST_PROTOCOL.md`, `docs/LIVE_TEST_RESULT_REDACTED.md`, evidence redacted hoặc lý do NOT_RUN.

**Gate:** Live tài khoản hợp pháp được kiểm thử mà không đụng đến dữ liệu ngoài quyền, không có file trùng/mất; nếu live bị BLOCKED thì không được tuyên bố full E2E PASS.

## PHASE 09 — Hardening, build Windows và release

**Mục tiêu:** Cung cấp bản nâng cấp đủ điều kiện sử dụng hàng ngày.

**Tasks**
1. Full regression tests trên Windows Python theo repo; smoke EXE onefile (nếu môi trường hỗ trợ), multi-tab/multi-account.
2. Test 10k và 100k metadata records (mock) với chuyển kỳ, filter, tìm kiếm; kiểm tra UI không freeze, memory/CPU và disk growth.
3. DB backup/recovery: lưu nhật ký migration version, integrity check, cảnh báo DB corrupt; hỗ trợ export DB/CSV và hướng dẫn backup; tuyệt đối không silent rebuild database làm mất dữ liệu.
4. UI polish: dấu “Đã tải/Thiếu/Chưa xác minh”, badge **Tổng kho** và **Trong kỳ**, “Lần đối soát gần nhất” có timestamp; trạng thái local không bị giả thành online mới nhất.
5. Export theo kỳ: mặc định lấy hồ sơ trong **view đang xem**, lựa chọn riêng “Xuất toàn bộ kho” nếu cần. Không xuất nhầm account.
6. App shutdown: flush writer, stop workers, commit checkpoint; không xóa DB/file.
7. Build theo `BUILD_WINDOWS.md`/PyInstaller spec, version bump và changelog; không lưu artifacts nhạy cảm vào release.
8. Smoke upgrade: cài/chạy EXE mới trên dữ liệu bản cũ (từ **bản sao backup**), dữ liệu vẫn còn; không cần tải lại.
9. Hướng dẫn người dùng phân biệt: **Đổi kỳ để xem đã lưu**, **Tra cứu để cập nhật danh mục từ thuế**, **Tra cứu và tải để bổ sung file**.
10. Bàn giao file `.exe`, source diff, test reports, backup/rollback guide khi có thể build thật; nếu không có Windows, bàn giao source + lệnh build, ghi rõ EXE `NOT_BUILT`.

**Deliverables:** `CHANGELOG.md`, `docs/DATABASE_GUIDE.md`, `docs/USER_GUIDE_LOCAL_SYNC.md`, `docs/ROLLBACK.md`, `docs/IMPLEMENTATION_PROGRESS.md`, EXE nếu build thành công.

**Gate:** Full required tests PASS, Windows smoke PASS (hoặc lý do NOT_RUN), không hồi quy tính năng hiện có, có plan rollback.

---

# E. MA TRẬN KIỂM THỬ NGHIỆM THU (BẮT BUỘC)

| ID | Scenario | Điều kiện PASS cụ thể |
|---|---|---|
| AC-01 | Xong tra cứu/tải | **Không** hiện “Sửa điều kiện”, form ngày vẫn thấy, ngày không reset |
| AC-02 | Đã có 2025 và 2026 → chọn 10/2026 | Bảng load data 10/2026 từ DB ngay; DB các năm không giảm |
| AC-03 | Chọn lại năm 2025 | Hiện đủ record 2025 và mở được file hợp lệ |
| AC-04 | Đóng/mở EXE | Lịch sử các năm tự khôi phục; đổi kỳ không cần HTTP |
| AC-05 | Local 100 + online 100 | Kết quả 100 key, không tạo thêm |
| AC-06 | Local 100 + online 105 | Kết quả 105 key, +5 mới |
| AC-07 | Local có 98 valid + 7 thiếu | Không download lại 98 valid; xử lý đúng 7 thiếu |
| AC-08 | Query online lỗi/empty/partial | Không xóa bất cứ record cũ nào; status rõ |
| AC-09 | Tờ khai bổ sung cùng kỳ | 2 remote IDs khác nhau đều còn, không merge nhầm |
| AC-10 | GNT và Thông báo | Phân tách mode; attachments giữ đúng linkage |
| AC-11 | Hai tài khoản | A không nhìn thấy B; không mix trong DB/query/download |
| AC-12 | File bị xóa/hỏng | Record còn; status missing/invalid, cho tải lại |
| AC-13 | Đổi kỳ nhiều lần nhanh | Worker cũ không ghi sai UI account/kỳ mới |
| AC-14 | Cancel giữa batch | Record/file đã commit còn nguyên, resume được |
| AC-15 | Migration dữ liệu cũ | File trước/sau SHA không đổi, DB count logic khớp, chạy lại không duplicate |
| AC-16 | Offline | Có thể duyệt local đúng account, không báo online thành công |
| AC-17 | Bấm đổi kỳ / gõ search | Network requests **= 0** |
| AC-18 | Kiểm thử 10k–100k rows | Không full-file-rehash trên UI filter, không freeze kéo dài |
| AC-19 | SQLite integrity | `PRAGMA integrity_check = ok`, không lỗi foreign key |
| AC-20 | Serial vs bounded concurrent | Metrics so sánh, không tăng corruption/auth errors, có fallback |
| AC-21 | Live test authorized | Chỉ báo PASS khi thật sự chạy, có kết quả redacted |
| AC-22 | Sau cập nhật EXE | DB ở vị trí bền vững, dữ liệu cũ còn, không nằm ở `_MEIPASS` |
| AC-23 | Kho và kỳ | Count `Tổng kho` không phụ thuộc kỳ; `Trong kỳ` thay theo date filter |
| AC-24 | Đổi nơi lưu | Không xóa kho cũ; quay lại thư mục cũ vẫn thấy dữ liệu |
| AC-25 | Export kỳ vs tất cả | Không lẫn scope và không xuất trùng |

**Thử nghiệm performance đề nghị (mock):** 100, 1.000, 10.000, 100.000 metadata rows; 10, 50, 100 file downloads giả lập; worker 1, 2, 3; latency các percentile; 0 request khi chỉ đổi date; đúng 0 request download đối với file valid cached. Các giá trị thời gian chỉ được điền sau đo, không tự đặt lời hứa tốc độ.

---

# F. UI/UX YÊU CẦU CUỐI

### F1. Thanh chọn kỳ LUÔN hiển thị

```text
[Tờ khai] [Giấy nộp tiền] [Thông báo thuế] [Phân tích XML]

Ngày nộp  [Tháng trước v]  Từ [01/10/2026]  Đến [31/10/2026]
Nơi lưu   [..........................] [Thay đổi] [Mở thư mục]
[Tra cứu] [Tra cứu và tải]

Kho dữ liệu: 2.505 hồ sơ  |  Trong kỳ: 105  |  Đã tải: 103  |  Thiếu: 2
Lần tra cứu online: 02/11/2026 10:00  |  Tác vụ mới nhất: +5 hồ sơ

[Tìm theo tên, mã hồ sơ, kỳ...]  [Trạng thái v]  [CQT v]
| Mã hồ sơ | Tên tờ khai | Kỳ tính thuế | Ngày nộp | Trạng thái file |
```

*Chỉ là wireframe; số liệu là ví dụ, không phải dữ liệu người dùng.*

### F2. Khi đổi kỳ

- Không yêu cầu bấm “Sửa điều kiện”.
- Không tự bấm Tra cứu, không tự tải.
- Local query tức thời theo database, có debounce UI nếu cần.
- `Kho dữ liệu` không đổi; `Trong kỳ` đổi.
- Khi chọn một kỳ chưa đồng bộ: hiện “Chưa có dữ liệu lưu trên máy trong kỳ này — bấm Tra cứu để đối soát từ cổng thuế”, **không** hiện “đã có đủ” chỉ vì không có row.
- Khi có hồ sơ local, hiển thị trước rồi vẫn cho Tra cứu để phát hiện bổ sung.

### F3. Khi bấm Tra cứu và tải

- Trong khi chạy giữ nguyên ngày, giữ rows local và thông báo progress.
- Cập nhật dần trong DB sau các batch hợp lệ.
- Khi xong, **vẫn giữ nguyên form ngày**, bảng phản ánh data đã upsert trong chính kỳ đang xem.
- Summary tác vụ: `Phát hiện online: n | Mới: x | Cập nhật: y | Đã có hợp lệ: z | Tải mới: k | Lỗi: e`.
- Không hiện “Sửa điều kiện” kể cả khi success/partial/cancelled.

---

# G. TĂNG CƯỜNG ĐỀ XUẤT (SAU KHI CORE ĐÃ PASS)

**P0 (trước release):**

- Tự backup database trước migration và trước chuyển schema; kiểm tra restore.
- Quản lý trạng thái “metadata có nhưng file thiếu/hỏng” không xóa record.
- Retry có giới hạn, resume sau bị dừng, log đã che dữ liệu nhạy cảm.
- Chỉ lưu trạng thái auth hợp lệ, tách local-view với online-login.
- Nút “Kiểm tra toàn vẹn” chủ động, không hash tất cả mỗi khi mở app.
- Mọi thao tác nguy hiểm như xóa bản ghi/import từ nguồn không rõ phải yêu cầu người dùng xác nhận; theo yêu cầu hiện tại **không thêm tính năng tự dọn/xóa**.

**P1 (nên làm sau ổn định):**

- “Kỳ chưa tra cứu gần đây” / “Lần đối soát online gần nhất”: hỗ trợ quyết định kỳ nào nên refresh, **không tự khẳng định dữ liệu đủ**.
- “Chỉ tải còn thiếu”, “Tải lại file lỗi”, “Tạm dừng/Tiếp tục” rõ ràng.
- Xuất báo cáo Excel theo kỳ/năm/toàn bộ kho; bảo toàn mô hình key.
- Tìm nhanh theo mã hồ sơ, tờ khai, kỳ tính thuế, CQT, trạng thái file.
- Kịch bản “quên nơi lưu”: chỉ tìm trong các roots từng được user chọn, có quyền và owner verified; không quét toàn ổ đĩa.
- Nút xem `Nhật ký đối soát`: mới, cập nhật, lỗi, file dùng lại.
- Cảnh báo OneDrive/network share đối với SQLite, hướng dẫn backup/copy an toàn khi đang đóng ứng dụng.

**Không làm khi chưa chứng minh:**

- Không tự đồng bộ ẩn mọi năm mỗi lần login.
- Không chạy vô hạn worker hoặc cố retry để né chặn CAPTCHA/rate-limit.
- Không xóa records “server không trả về” nếu query không chứng minh đã phủ đủ tất cả nguồn/trang.
- Không đặt mật khẩu/session vào SQLite, JSON metadata, report, screenshot, issue hoặc CI artifacts.
- Không đổi stack sang web app hay cloud DB nếu desktop SQLite đáp ứng.

---

# H. ĐỊNH NGHĨA HOÀN THÀNH CHO CODING AGENT

Chỉ báo `COMPLETE` khi:

1. **Source thực đã được sửa** và toàn bộ diff liên quan giải quyết không có “Sửa điều kiện”, giữ ngày sau tải.
2. **SQLite hoạt động**: 2025/2026 giữ xuyên suốt thay đổi khoảng ngày, restart EXE và tra cứu lại.
3. **Migration chạy thành công trên fixture dữ liệu cũ** mà không mất file hoặc tạo trùng.
4. **Smart sync** trả về upsert đúng, skip file valid, retry missing, không xóa khi failed/partial.
5. Test unit/integration/regression đạt; report lệnh test thực tế và log kết quả.
6. Performance có baseline, optimized, request count và benchmark, không ghi mức tăng tốc tưởng tượng.
7. Live test với một account **được cấp quyền** có kết quả redacted; nếu chưa thể chạy thì minh bạch ghi `NOT_RUN`, không bịa.
8. Build EXE Windows smoke-pass nếu có Windows; nếu không có, đánh dấu `NOT_BUILT` và bàn giao build script.
9. Có tài liệu user guide, rollback, progress, báo cáo security review.

**Báo cáo cuối agent bắt buộc theo mẫu:**

```markdown
# IMPLEMENTATION REPORT
Commit/base:
Branch:
Files changed:
DB location/schema:
Migration result (dry-run/real):
UI fix evidence:
Multi-year persistence evidence:
Dedup evidence:
Missing-download skip evidence:
Performance before/after (with numbers):
Live test: PASS / FAIL / NOT_RUN (reason):
Unit/integration regression: PASS / FAIL counts:
Windows EXE: BUILT+SMOKE_PASS / NOT_BUILT / FAILED:
Known limitations:
Rollback steps:
```

**Ưu tiên cuối cùng:** Chất lượng, **không mất một tờ khai nào đã lưu**, và tránh tráo “view đang xem” với “kho dữ liệu đầy đủ”. Nếu phải lựa chọn giữa tốc độ và toàn vẹn, **giữ toàn vẹn trước**. Tối ưu đa luồng chỉ sau khi persistence và smart sync đã đạt toàn bộ Gate của PHASE 01–05.
