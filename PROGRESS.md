# Tiến độ sửa 26 mục core

Đã merge đủ **26/26 mục** vào `main`, cùng nhánh tài liệu review !4 và
`feat/legacy-notices-pre2015`. Desktop 2.0.2 sửa luồng nâng cấp thư mục cũ:
tự chọn `tai-moi` nếu chưa có owner, không gán lại hoặc thay đổi dữ liệu cũ.
Giữ thông báo legacy, XML/ZIP cũ, sửa chỉ số Qt và các prompt riêng ở checkout gốc.

- Kiểm thử tích hợp: 707 tests, 701 đạt và 6 skip OCR tùy chọn; Qt/default OCR chạy.
- Ruff toàn checkout và mypy core/concrete contracts đạt (90 file).
- Chi tiết: [legacy và hồ sơ trước 2015](docs/LEGACY_NOTICES_PRE2015.md).
- Snapshot truy vết từng MR: [RESUME.md](docs/core-hardening/RESUME.md).
- Build theo `scripts/build_windows.ps1`, chỉ nhận kết quả khi inventory,
  desktop gate, audit, source/frozen OCR và ma trận UI đều đạt. Bằng chứng
  build thực tế ở `dist/release-manifest.json` và `.cache/last-smoke-path.txt`.
- Không tự publish hoặc thay release/tag công khai. Kiểm tra dữ liệu thật
  trước 2015 chưa thực hiện; không suy ra cổng đã xóa hồ sơ khi trả rỗng.
- Kiểm thử online có yêu cầu riêng qua `--online-check <request.json>`,
  không tự chạy; nhận credential từ `.env` có sẵn và chỉ xuất metadata.
  Giới hạn 3 khoảng tối đa 31 ngày, 300 giây/120 request/128 MiB/15 trang;
  mỗi khoảng tối đa 1 hồ sơ, kèm 1 lượt kiểm reuse nếu tải đủ. Không nộp hồ sơ.
