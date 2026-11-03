# Tiến độ sửa 26 mục core

## Windows 2.1.2 và cá nhân ưu tiên DVC — 03/11/2026

Đã lấy GitHub `main` 9098ae2, giữ nguyên nhánh/lịch sử GitLab cũ và sửa trên
`fix/personal-dvc-login`. Code build tại `da7dcf2`: cá nhân dùng DVC từ cutoff,
cổng cá nhân cũ trước cutoff; sửa nhận diện lỗi tài khoản, giữ phiên DVC riêng,
CLI chọn adapter cá nhân và kiểm tra cập nhật chuyển sang GitHub.

968 tests (6 skip OCR tùy chọn), ruff, mypy, dependency inventory, audit bundle,
source/frozen OCR, hai lượt offline standalone và đủ 18 cấu hình UI đều đạt.
EXE kiểm tra online: cá nhân 8 tờ khai DVC; doanh nghiệp 15 tờ khai DVC,
12 GNT, 7 thông báo; mỗi nhóm tải thử 1 và reuse 1 thành công.
GNT cá nhân vẫn chưa hỗ trợ. Chưa push/phát hành bản build này.
Chi tiết/hash: [báo cáo kiểm chứng 2.1.2](docs/PERSONAL_DVC_WINDOWS_20261103.md).

## Sửa lỗi DVC 2.0.4 — 22/10/2026

Đã tái hiện lỗi `lan_nop` trên DVC thật, bổ sung tiêu đề mới và xử lý đúng
hàng thiếu ô đính kèm tùy chọn ở cuối. Source kiểm tra DVC 09/2026 (24 hồ sơ),
01–22/10/2026 (10 hồ sơ), legacy 06/2025 (2 hồ sơ), đều SUCCESS. Build EXE
chỉ được bàn giao sau gate và kiểm thử frozen riêng.
Chi tiết và giới hạn: [DVC_SCHEMA_FIX_20261022.md](docs/DVC_SCHEMA_FIX_20261022.md).
Theo yêu cầu review toàn bộ nhóm lỗi tương tự, đã sửa thêm lỗi scope ETAX thật
và các lỗi tổng hợp về thông báo, HTML ẩn, CAPTCHA, phân trang, ID GNT.
Source ETAX 06/2025 đọc 2 hồ sơ; GNT 09/2026 đọc 12 và TB đọc 7 thành công.
12 phương thức regression mới: 11 thất bại trên snapshot trước review, cả 12
đạt sau sửa. Xem [báo cáo review](docs/SCHEMA_REVIEW_20261022.md).

## Lịch sử tích hợp

Đã merge đủ **26/26 mục** vào `main`, cùng nhánh tài liệu review !4 và
`feat/legacy-notices-pre2015`. Desktop 2.0.2 sửa luồng nâng cấp thư mục cũ:
tự chọn `tai-moi` nếu chưa có owner, không gán lại hoặc thay đổi dữ liệu cũ.
Giữ thông báo legacy, XML/ZIP cũ, sửa chỉ số Qt và các prompt riêng ở checkout gốc.

- Bản 2.0.3: sửa crash `NoneType.get` do HTML ẩn lồng nhau; nhận hai tiêu đề
  GNT dài và chỉ bỏ đúng khối tổng tiền cuối bảng (5/1/1/13 cột). Kiểm thử
  nguồn có quyền: GNT 09/2026 tra cứu, tải một XML, dùng lại tệp đều thành công.
- Thêm danh sách công ty khi bấm MST, tự điền mật khẩu; tùy chọn lưu sau đăng
  nhập thành công bằng Windows Credential Manager, nút quên từng tài khoản.
  Không lưu mật khẩu trong settings/log/JSON; giữ quy tắc đổi phiên/tài khoản.
  Xem [hướng dẫn và kiểm thử kho Windows](docs/SAVED_ACCOUNTS.md).
- Smoke source/frozen bổ sung lỗi HTML/GNT và vòng lưu/đọc/chọn/cập nhật/xóa
  hai tài khoản giả trong kho Windows. Bằng chứng 2.0.3 chỉ có hiệu lực sau khi
  build/gates ở trên cùng source SHA; chưa công bố release/tag.

- Kiểm thử 2.0.3: 723 tests, 717 đạt và 6 skip OCR tùy chọn; Qt/default OCR chạy.
  Profile minimal: 723 tests, 43 skip đúng các thành phần tùy chọn.
- Ruff toàn checkout và mypy core/concrete contracts đạt (90 file).
- Chi tiết: [legacy và hồ sơ trước 2015](docs/LEGACY_NOTICES_PRE2015.md).
- Snapshot truy vết từng MR: [RESUME.md](docs/core-hardening/RESUME.md).
- Build theo `scripts/build_windows.ps1`, chỉ nhận kết quả khi inventory,
  desktop gate, audit, source/frozen OCR và ma trận UI đều đạt. Bằng chứng
  build thực tế ở `dist/release-manifest.json` và `.cache/last-smoke-path.txt`.
- Không tự publish hoặc thay release/tag công khai. Đã kiểm tra online có quyền:
  7 hồ sơ 01/2020, 1 ZIP + 2 XML thông báo và reuse. Khoảng 12/2014, 01/2013
  trả rỗng có xác nhận; chưa có mẫu tệp trước 2015, không suy ra cổng đã xóa hồ sơ.
- Kiểm thử online có yêu cầu riêng qua `--online-check <request.json>`,
  không tự chạy; nhận credential từ `.env` có sẵn và chỉ xuất metadata.
  Giới hạn 3 khoảng tối đa 31 ngày, 300 giây/120 request/128 MiB/15 trang;
  mỗi khoảng tối đa 1 hồ sơ, kèm 1 lượt kiểm reuse nếu tải đủ. Không nộp hồ sơ.
