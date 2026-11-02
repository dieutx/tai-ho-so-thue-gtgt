# Kết quả đo local

Windows x64 / CPython 3.11.15; synthetic metadata, median 5 warm reads. Lệnh: `.venv-release/Scripts/python.exe scripts/benchmark_local_catalog.py --output .cache/persistent-catalog-benchmark.json`.

| Tổng rows | Rows tháng 10/2026 | JSON scan ms | SQLite SELECT ms | SQLite ingest giây |
|---:|---:|---:|---:|---:|
| 100 | 4 | 0.600 | 0.415 | 0.0160 |
| 1.000 | 41 | 5.759 | 0.877 | 0.1011 |
| 10.000 | 416 | 60.839 | 4.741 | 1.0114 |
| 100.000 | 4.166 | 600.132 | 46.053 | 10.5682 |

Tất cả SELECT trả đúng tập RecordKey của JSON; `integrity_check=ok`. Lọc local: 0 HTTP, 0 deep-file-read. Chưa bao gồm paint Qt hoặc stat nhiều tệp trên ổ mạng. Không khẳng định thời gian render UI dựa vào số SELECT.

Smart-sync mock: 105 hồ sơ, 98 valid reused, đúng 7 download calls; đồng bộ lại reused=105, download calls=0, inventory=105. Đây là kiểm chứng request reuse, không phải bằng chứng tốc độ truyền mạng tăng. HTTP metrics mới chỉ ghi category allowlist, status class, số byte và tối đa 2.048 latency samples (p50/p95); không URL/payload/cookie/token.

Live performance và workers 2/3: NOT_RUN, chưa có cơ sở bật đa luồng.
