# Baseline và phương pháp đo

Desktop baseline trước sửa: 887 tests PASS (6 skips), 37.898s; kiểm thử này không đo tốc độ cổng thuế. Library trước nâng cấp đọc JSON đầy đủ rồi lọc memory; checkpoint JSON đã có sẵn. Tải lại valid artifacts vốn đã được core skip, vì vậy không tuyên bố nâng cấp mới giảm request cho hành vi vốn đã tối ưu.

`scripts/benchmark_local_catalog.py`: synthetic metadata 100/1k/10k/100k rows, cùng RecordKey và phân bố ngày trên 24 tháng 2025–2026. So thời gian đọc JSON đầy đủ+lọc với indexed SELECT tháng 10/2026, median 5 warm reads. Không hash file, không network. Đây là phép đo hai đường đọc tương đương, không phải phép đo đầu-cuối bản EXE cũ/mới.

`tests/test_local_catalog.py::IncrementalPipelineTests`: pipeline GNT thật, portal giả; 100 metadata local + 105 online, 98 artifacts valid. Đếm call download trực tiếp, không suy từ trạng thái UI. Lượt đầu cần 7, lượt sau 0. Download implementation vẫn tuần tự; chưa có số đo workers 2/3 hay tốc độ live.
