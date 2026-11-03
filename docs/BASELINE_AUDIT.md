# Baseline nâng cấp kho local — 02/11/2026

- Base: `ca4b220a455153941a5a1cead69e96d8622be4ea`, nhánh gốc `feat/legacy-notices-pre2015`.
- Source desktop thực tế: 2.0.3; core 1.0.0. Nhánh triển khai: `feature/persistent-catalog-smart-sync`.
- Ban đầu có thay đổi của người dùng ở `desktop/resources/release.json` và file kế hoạch chưa tracked. Bản release metadata ban đầu và EXE cũ được sao lưu vào `.cache/persistent-upgrade/` trước build. Không sửa `.env` hoặc dữ liệu thuế thật.
- Môi trường: Windows x64, CPython 3.11.15. `.venv` thiếu pypdf: chạy đầu tiên 430 tests, 41 import errors, 29 skips; đây là lỗi môi trường. Dùng `.venv-release` đã có đủ dependency, không đổi dependency locks.
- Baseline chính: `.venv-release/Scripts/python.exe scripts/run_test_gate.py --profile desktop`: **887 tests, OK, 6 skips**, 37.898 giây. Log: `.cache/persistent-baseline-desktop.txt`.

Đường đi cũ: portal → pipeline → JSON catalog/checkpoint → `JobResult` → `TabState` → `RecordsModel`. JSON có merge lịch sử nhưng bảng chỉ giữ một job. `ui.launch(clear=True)` xóa view; `on_completed()` reset model bằng rows của job rồi gọi `collapse_conditions(True)`. Đổi ngày chỉ lọc proxy khi operation=library; luồng online không đọc lại toàn kho. Library cũ cũng chưa xác minh ownership thư mục.

Đường đi mới: portal → checkpoint SQLite từng hồ sơ → tệp atomic + evidence → checkpoint → export JSON/Excel tương thích → SELECT SQLite theo kỳ đang hiển thị. Metadata và file trạng thái sau deep verify được lưu trước khi worker trả kết quả. SQLite inventory không bị replace theo view.

An toàn thử nghiệm: toàn bộ migration/unit/benchmark dùng thư mục TemporaryDirectory và hồ sơ tổng hợp; test migration lưu SHA-256 JSON/ZIP trước/sau và kiểm chứng không đổi byte. Không chạy migration trên `download/` hay dữ liệu của người dùng để tạo baseline. DB backup bằng SQLite backup API trước import. Các tài liệu/số đo tổng hợp có thể commit; log và workspace live giữ ngoài Git.
