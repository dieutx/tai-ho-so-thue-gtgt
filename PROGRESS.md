# Tiến độ sửa 26 mục core

Đã merge đủ **26/26 mục** vào `main`, cùng nhánh tài liệu review !4 và
`feat/legacy-notices-pre2015`. Desktop 2.0.1 bổ sung thông báo tờ khai legacy,
XML/ZIP cũ và sửa chỉ số bảng Qt. Giữ các prompt/tệp riêng ở checkout gốc.

- Kiểm thử tích hợp: 699 tests, 693 đạt và 6 skip OCR tùy chọn; Qt/default OCR chạy.
- Ruff toàn checkout và mypy core/concrete contracts đạt (90 file).
- Chi tiết: [legacy và hồ sơ trước 2015](docs/LEGACY_NOTICES_PRE2015.md).
- Snapshot truy vết từng MR: [RESUME.md](docs/core-hardening/RESUME.md).
- Build theo `scripts/build_windows.ps1`, chỉ nhận kết quả khi inventory,
  desktop gate, audit, source/frozen OCR và ma trận UI đều đạt. Bằng chứng
  build thực tế ở `dist/release-manifest.json` và `.cache/last-smoke-path.txt`.
- Không tự publish hoặc thay release/tag công khai. Kiểm tra dữ liệu thật
  trước 2015 chưa thực hiện; không suy ra cổng đã xóa hồ sơ khi trả rỗng.
