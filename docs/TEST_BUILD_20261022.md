# Bản test nội bộ 2.0.2 — 22/10/2026

Nhánh `feat/desktop-test-build` xuất phát từ `main` GitLab tại `96d3460`.
Bản này dành cho người dùng test, chưa tạo tag hay upload Release/Package.

## Nâng cấp

- Danh sách cập nhật theo định danh từng hồ sơ và gom tiến độ mỗi 100 ms,
  giữ checkbox, index và dòng đang xem khi có kết quả mới; không reset toàn
  bộ bảng ở từng sự kiện. Cập nhật cuối được flush trước khi nhận tổng kết.
- XML Viewer tự vừa vùng làm việc và chia nút thao tác thành hai hàng.
  Smoke native của EXE kiểm tra cả cửa sổ XML trong 18 cấu hình màn hình/DPI.
- Thêm regression cho cập nhật trùng, phân biệt nguồn, giữ index/checkbox,
  sort/filter sau cập nhật, burst 500 hồ sơ và dừng timer khi kết thúc.

Benchmark model tại Windows/Python 3.11/Qt 6.8.3, 5.000 hồ sơ và 100 lượt cập
nhật: baseline reset **4,2443 giây**, cập nhật từng dòng **0,0071 giây**.
Đây là phép đo tầng model với dữ liệu tổng hợp, không phải tốc độ mạng/cổng thuế.

## Các thao tác cần test

1. Tra cứu một khoảng có nhiều hồ sơ; kéo bảng hoặc chọn dòng khi danh sách
   đang cập nhật, kiểm tra dòng đang xem và checkbox được giữ.
2. Tìm kiếm/lọc trạng thái khi đang tra cứu; hồ sơ mới hoặc đổi trạng thái
   phải vào/ra đúng bộ lọc, không tạo dòng trùng cùng mã và cùng nguồn.
3. Tải các tệp đã chọn rồi Dừng; kiểm tra tổng kết và thử lại. Tệp đã tải
   hợp lệ vẫn được dùng lại theo cơ chế hiện có.
4. Mở phản hồi CQT hoặc thông báo XML ở DPI 125%/150%, kiểm tra hai tab
   nội dung, sao chép, lưu và nút Đóng đều thao tác được.

Build bằng `scripts/build_windows.ps1` với runtime/tooling đã kiểm tra
inventory. Script chạy full desktop gate, lint, mypy, bundle audit, OCR/offline
self-test và smoke native trước khi tạo receipt/hash. Kết quả cuối đi kèm
EXE ở thư mục `dist` của bản test; không dùng script publish/replace.
