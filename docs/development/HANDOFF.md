# Bàn giao: tiếp tục trên máy khác

Cập nhật: **27/09/2026**. Repo private:
`https://gitlab.com/dieutx/tai-ho-so-thue-gtgt.git`, nhánh bàn giao `main`.
Baseline trước đợt thay đổi: `a9e7223`. Xem `git log -5 --oneline` để biết
commit mới nhất; tài liệu này được version cùng code, không gắn hash tự tham chiếu.

## 1. Mục tiêu và trạng thái thực tế

Yêu cầu: trước cutoff dùng trực tiếp legacy, tạm tắt DVC nhưng có thể mở lại;
làm nền tảng phân loại file và parser từng nhóm; có master/detail prompt để
phát triển từng lần, kiểm thử thật và chuyển máy không mất tiến độ.

Đã triển khai:

- Mặc định `legacy_etax=True`, `dvc_enabled=False`. Trước cutoff dùng legacy;
  đúng ngày cutoff thuộc DVC. DVC tắt thì không login/CAPTCHA/search DVC,
  đoạn sau cutoff bị báo bỏ qua và kết quả không đầy đủ (exit 1).
- Ngày mặc định là đầu tháng chứa ngày trước cutoff tới ngày trước cutoff;
  với cutoff `01/07/2025` là `01/06/2025`–`30/06/2025`. Ngày đã có trong `.env`
  vẫn được giữ; không tự sửa cấu hình riêng của người dùng.
- Sửa dry-run không đổi tên ZIP, case-id thất bại còn được thử ở đoạn sau,
  dò tên ZIP tránh khớp nhầm mã con, phát hiện trang lặp/rỗng bất thường.
- Legacy nhận kết quả rỗng hợp lệ, giữ form khi gặp HTML lỗi, sửa Origin,
  kiểm XML well-formed và chặn HTML/DTD trước khi gói ZIP.
- Metadata gộp theo `(nguon, ma_ho_so)`, giữ dòng cũ/trường lạ, không ghi đè
  JSON hỏng. Ghi atomically từng file; chưa có transaction chung ba file.
- Rule `metadata-keyword-v1`: GTGT/TNCN/TNDN/OTHER/UNKNOWN và vai trò tài liệu,
  có lý do/version; tạo `phan_loai_ho_so.json`. Không di chuyển file ZIP cũ.
- Validate retry/timeout/pause; bổ sung che trường legacy; đóng log handler
  của CLI để test Windows không giữ file mở.
- Có REVIEW, bản đồ kiến trúc, master prompt và 9 prompt stage.

**Chưa xong:** stage 01 còn hardening; chưa có inventory từng file trong ZIP,
classifier nội dung hoặc parser chỉ tiêu GTGT/TNCN/TNDN. `parsing.py` đọc bảng
HTML tra cứu, không phải parser XML thuế. Một nhóm của hồ sơ không chứng minh
mọi file đính kèm có cùng nhóm. DVC vẫn hoãn, chưa xác minh lại cổng hiện tại.

## 2. Quá trình và bằng chứng kiểm thử

1. Rà soát repo và baseline: 269 test, 8 skip OCR, 4 lỗi đóng log trên Windows;
   lint/mypy baseline qua. Giữ nguyên dữ liệu và môi trường cũ.
2. Sửa policy nguồn và lỗi logic, thêm test regression và rule phân nhóm.
3. Chạy offline: 297 test OK, ruff qua, mypy qua 34 file. Trước cài OCR có
   8 skip; lần kiểm tra cuối với `ddddocr` có 6 skip backend chưa cài.
4. Theo yêu cầu người dùng, test thật bằng `.env` trên legacy: 6/6 hồ sơ,
   6 ZIP hợp lệ và 6 XML well-formed, không gọi DVC.
5. Chạy lại cùng khoảng: 6/6 hồ sơ dùng ZIP sẵn, **0 request tải lại**, không
   gọi DVC, metadata không tăng trùng. Cập nhật README và bàn giao trước commit/push.

Chi tiết và giới hạn trong [REVIEW](REVIEW.md). Chưa kiểm tra lại CI Linux
Python 3.10/3.12; xem pipeline GitLab của commit sau push, không suy ra CI xanh
từ test Windows. Không cần gọi lại tài khoản thật để chạy unit test.

Môi trường kiểm chứng tại máy cũ: Windows, Python 3.11.15, beautifulsoup4
4.15.0, lxml 6.1.3, requests 2.34.2, ddddocr 1.6.1, onnxruntime 1.30.0,
ruff 0.16.9, mypy 2.3.1. Đây là phiên bản quan sát, **không phải lockfile**;
requirements hiện là khoảng phiên bản. Máy mới cần chạy lại test sau cài.

`.venv` máy cũ tham chiếu Python đã bị gỡ, nên đợt kiểm tra dùng môi trường
riêng `.venv-review`. Không mang cả hai thư mục này sang máy mới.
Git máy cũ cũng chưa có `user.name`/`user.email`; hai commit bàn giao dùng
danh tính tác giả commit gần nhất qua tùy chọn riêng từng lệnh, không sửa
cấu hình Git toàn máy. Máy mới cần cấu hình danh tính của chính bạn trước commit.

## 3. Dựng lại trên Windows / PowerShell

Cần Git, Python 3.11 (hoặc bản được repo hỗ trợ) và quyền truy cập GitLab private.
Dùng credential manager/SSH key hoặc token có quyền phù hợp; không đưa token
vào URL clone, `.env`, tài liệu hay lệnh được lưu trong Git.

Clone mới:

```powershell
git clone https://gitlab.com/dieutx/tai-ho-so-thue-gtgt.git
cd tai-ho-so-thue-gtgt
git status --short --branch
git log -5 --oneline
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` gồm dependency ứng dụng, OCR mặc định và lint/typecheck.
Dùng trực tiếp Python trong venv, không cần Activate hay đổi execution policy.
Trước khi commit trên máy mới, đặt danh tính Git riêng cho repo bằng
`git config --local user.name "Tên của bạn"` và
`git config --local user.email "email-cua-ban@example.com"` (thay placeholder
bằng email/noreply của chính bạn). Danh tính commit khác thông tin xác thực push.

Nếu chỉ sửa/test offline, thay lệnh cài cuối bằng:

```powershell
.\.venv\Scripts\python.exe -m pip install beautifulsoup4 lxml requests ruff mypy
```

Nếu đã có clone trên máy mới: kiểm tra `git status` trước, giữ/commit thay đổi
riêng, rồi `git switch main` và `git pull --ff-only origin main` khi worktree
sạch. Nếu pull báo diverged, xem `git log --graph --oneline --all`; không
`reset --hard`, không force push. Dùng Python được cài tại máy đó để tạo venv mới.

Kiểm chứng trước làm tiếp:

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy gdt_tax
git diff --check
```

Linux/macOS: `python3 -m venv .venv`, `source .venv/bin/activate`, rồi dùng
`python -m pip`/`python -m ...` với các lệnh tương đương. Test không cần `.env`,
tài khoản hay Internet; test OCR không có dependency được skip.

## 4. Những gì Git không chuyển sang máy mới

| Nội dung | Cách xử lý |
|---|---|
| `.env` và credentials/proxy | Chuyển bằng kênh riêng an toàn hoặc tạo lại từ `.env.example`; không dán vào chat/issue/commit |
| `download/` | Nếu muốn resume, chuyển cả ZIP và `danh_sach_ho_so.json`, `.csv`, `phan_loai_ho_so.json` cùng thư mục |
| `logs/`, HTTP dump, live-test harness/report | Chỉ chuyển riêng khi cần điều tra; không có sẵn sau clone và không an toàn để chia sẻ thô |
| `.venv`, `.venv-review`, `.cache` | Không chuyển; cài lại môi trường trên máy mới |

Nếu không chuyển download cũ, dùng thư mục mới và chấp nhận tải lại; không tự
tạo metadata giả. Trước chuyển, dừng tiến trình ghi file và sao lưu thư mục.
Mỗi tài khoản dùng thư mục output riêng; identity hiện chưa đủ an toàn để
trộn nhiều tài khoản/nguồn và không hỗ trợ nhiều tiến trình ghi đồng thời.

Chỉ trên clone mới **chưa có `.env`**:

```powershell
Copy-Item .env.example .env
```

Điền tài khoản legacy riêng, giữ `GDT_DVC_ENABLED=false`,
`GDT_LEGACY_ETAX=true`, ngày được cho phép trước cutoff và đường dẫn output.
Không ghi đè `.env` đã có. Biến `GDT_*` trong môi trường shell thắng `.env`;
nếu chạy lệch cấu hình, kiểm tra tên biến được set và sửa đúng biến, không
in toàn bộ môi trường vì có thể lộ mật khẩu.

Chỉ khi được yêu cầu test thật, chạy khoảng nhỏ đã được cho phép. Ví dụ tái
lập đúng khoảng đã kiểm chứng, nếu vẫn có quyền dùng tài khoản đó:

```powershell
.\.venv\Scripts\python.exe -m gdt_tax --from-date 01/09/2018 --to-date 25/10/2018 --disable-dvc --legacy-etax
```

`--dry-run` vẫn đăng nhập/tra cứu thật và có thể ghi metadata, không tải/đổi
tên ZIP. Muốn không ảnh hưởng metadata cũ khi thăm dò, dùng output riêng.
Không bật HTTP dump mặc định; log/dump riêng tư không được commit. Việc mở
DVC cần một nhiệm vụ riêng ở stage 09, không bật chỉ để tránh warning.

## 5. Đọc code ở đâu

| Cần hiểu/sửa | Điểm bắt đầu |
|---|---|
| Đọc `.env`, ưu tiên override, policy nguồn | `gdt_tax/config.py`, `constants.py`, `tests/test_config.py` |
| Flags CLI, exit code, vòng đời log | `gdt_tax/cli.py`, `logging_setup.py`, `tests/test_cli.py` |
| Chia ngày, trang, tải/resume, summary | `dates.py`, `pipeline.py`, `models.py`, `tests/test_pipeline.py` |
| Login/HTML/XML legacy | `portals/etax_legacy.py`, `tests/test_etax_legacy.py` |
| ZIP, metadata merge, index nhóm | `storage.py`, `tests/test_storage.py` |
| Phân nhóm từ metadata | `classification.py`, `tests/test_classification.py` |
| Raw log/dump, HTTP/retry | `traffic.py`, `http.py`, các test tương ứng |
| Việc chưa làm và hướng triển khai | `REVIEW.md`, `README.md` trong thư mục này, `prompts/` |

## 6. Nhịp làm việc mỗi lần

1. Đọc git status, tài liệu bàn giao và stage hiện tại; chạy baseline. Nêu rõ
   phần đã có để không triển khai trùng hoặc đụng thay đổi riêng.
2. Chọn **một stage**, gửi [MASTER](prompts/MASTER.md) + prompt stage tương ứng.
   Nếu stage lớn, chốt một phần nhỏ và tiêu chí kiểm chứng; stage vẫn ghi chưa xong.
3. Sửa code cùng regression test/fixture ẩn danh. Chạy offline trước; không
   dùng tài khoản thật trong unit test, không bịa schema/XPath/chỉ tiêu thuế.
4. Chạy unittest/ruff/mypy, cập nhật README/ARCHITECTURE/REVIEW/HANDOFF và bảng
   stage: đã làm, còn thiếu, kết quả test, bước kế tiếp.
5. Xem `git diff`, `git diff --check`, chỉ stage file cần thiết; kiểm tra diff
   staged không có secrets/data thật. Commit mô tả hành vi và kiểm chứng;
   push khi được yêu cầu, kiểm tra remote và CI. Không force push.

Tiếp theo ưu tiên phần còn thiếu **stage 01** trong REVIEW: bảo vệ log/dump,
giới hạn ZIP/XML, identity/resume, auth/retry/config. Sau đó 02 inventory → 03
classifier → 04 parser core → 05 một mẫu GTGT có fixture → 06 TNCN → 07 TNDN
→ 08 export. Stage 09 DVC hoãn và không chặn 02–08.

Các mẫu thật vừa thấy: `04/GTGT`, `02TH`, `BC26/AC`. Cần inventory và fixture
ẩn danh trước khi thêm rule/parser; hiện hai mẫu sau còn UNKNOWN. Không lấy
kết quả 6/6 tải xuống làm bằng chứng parser hay phân loại nội dung đã hoàn thành.

Prompt ngắn để mở phiên làm việc trên máy mới (gửi kèm master + stage 01):

```text
Đọc README.md, docs/ARCHITECTURE.md, docs/development/HANDOFF.md,
REVIEW.md và README.md trong docs/development, kiểm tra git status và baseline.
Tiếp tục phần còn thiếu của stage 01 theo master/detail prompt; không làm lại
policy legacy trước cutoff hoặc classifier metadata đã có. Giữ DVC mặc định
tắt và không gọi DVC khi tắt. Chọn phạm vi hardening nhỏ có test, triển khai,
chạy unittest/ruff/mypy và cập nhật tài liệu tiến độ/bàn giao. Chưa chuyển sang
parser hay stage tiếp theo. Không in secrets hoặc đưa data thật vào Git;
chỉ test tài khoản thật hoặc commit/push khi tôi yêu cầu.
```
