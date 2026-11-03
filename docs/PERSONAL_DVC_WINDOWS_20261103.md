# Cá nhân/DVC và Windows 2.1.2 — 03/11/2026

Mã nguồn build: `da7dcf2fc2dcb6dfd205077e2d33d4e397db5223`, nhánh
`fix/personal-dvc-login`, dựa trên GitHub `main` tại `9098ae2`.
Remote `origin` trỏ GitHub; remote GitLab và nhánh làm việc cũ được giữ lại.

## Những lỗi đã sửa

- Cá nhân bị ép cutoff tới năm 2100, tắt DVC và dùng cổng cũ cho mọi kỳ.
  Giờ dùng DVC từ cutoff (mặc định 01/07/2025), cổng cá nhân cũ trước cutoff.
  Khoảng đi qua cutoff giữ kết quả của cả hai nguồn.
- Thông báo DVC `status=401` với nội dung “Thông tin tài khoản hoặc mật khẩu
  không đúng” bị nhận thành `AUTH_SCHEMA_UNKNOWN`. Giờ trả
  `AUTH_INVALID_CREDENTIALS`, dừng ngay, không thử lại bằng cổng khác.
- DVC cá nhân giữ cookie riêng và dùng lại phiên giữa đăng nhập/tra cứu/tải;
  chỉ xác thực lại tối đa một lần khi cổng xác nhận hết phiên.
- CLI chọn đúng adapter cá nhân, thêm `--account-type CN`; GNT cá nhân dừng
  với `UNSUPPORTED_ACCOUNT_FLOW` trước khi gửi request doanh nghiệp.
- Kiểm tra cập nhật, thông báo trong app và link tải chuyển từ GitLab sang
  GitHub Releases. Bỏ qua draft/prerelease và mở trang release nếu thiếu EXE.
- Chẩn đoán `--online-check` nhận `account_type` và proxy, chạy qua Worker
  thật của ứng dụng. Mật khẩu không nằm trong file yêu cầu hay báo cáo.

## Kiểm chứng online trên EXE

Các lượt đều chạy EXE 2.1.2 đóng gói, cùng source SHA ở trên. Mỗi lượt đăng
nhập, tra cứu toàn kỳ, tải chọn lọc một hồ sơ rồi chạy lại để kiểm tra reuse.
Không nộp, sửa hoặc xóa hồ sơ trên cổng thuế.

| Tài khoản / nhóm | Kỳ | Tìm thấy | Tải thử | Dùng lại | Kết quả |
|---|---|---:|---:|---:|---|
| Cá nhân — tờ khai DVC | 01–31/10/2026 | 8 | 1 | 1 | SUCCESS |
| Doanh nghiệp — tờ khai DVC | 01–31/10/2026 | 15 | 1 | 1 | SUCCESS |
| Doanh nghiệp — giấy nộp tiền | 01–30/09/2026 | 12 | 1 | 1 | SUCCESS |
| Doanh nghiệp — thông báo | 01–30/09/2026 | 7 | 1 | 1 | SUCCESS |

Tất cả dùng CAPTCHA tự động; không cần nhập tay. Lượt cá nhân trên source
cũng có cùng kết quả 8/1/1. CAPTCHA giữ độ dài 5 ký tự và cơ chế 5 lần OCR rồi
nhập tay; lỗi tài khoản không bị coi là lỗi CAPTCHA để thử liên tục.

Bằng chứng cục bộ đã lược thông tin tài khoản:
`.cache/personal-dvc-live-source.json`, `.cache/personal-frozen-verification.json`,
`.cache/company-frozen-verification.json`. Dữ liệu tải thật nằm trong `.cache`
riêng, không đưa vào Git hoặc bundle.

## Build và kiểm thử

- Bộ desktop: 968 tests, 962 đạt, 6 bỏ qua do không cài EasyOCR/PaddleOCR tùy chọn.
  Qt, ddddocr và ONNX mặc định đều được kiểm thử.
- Ruff toàn repo đạt; mypy core/concrete contracts đạt trên 95 file.
- Dependency runtime/tools đúng inventory; `pip check` không có lỗi.
- Audit bundle đạt: model OCR đúng hash nguồn, đủ runtime, không thiếu module.
- Smoke source và hai lượt EXE standalone đều đạt: OCR/model/charset/provider
  khớp, fallback CAPTCHA có giới hạn, SQLite và Windows Credential Manager đạt.
- Giao diện native Windows: đủ 18 cấu hình (6 kích thước × 100/125/150%) đạt.
  Bằng chứng: `.cache/smoke-726d786720604e01856b1b9b01678ea3/`.
- Build kết thúc mã 0; provenance đối chiếu source SHA, gate, audit và smoke đạt.

Lệnh build dùng đầy đủ smoke/provenance, không dùng `-SkipSmoke`:

```powershell
./scripts/build_windows.ps1 -Python .venv-release/Scripts/python.exe -ToolsPython .venv-release-tools/Scripts/python.exe -SkipInstall
```

Artifact: `dist/TaiHoSoThue-Windows.exe`, 90.457.512 bytes.
SHA-256: `514959b5028f851a91e154daad10197f7277dfe4c7e2e2f4bf31ce41b132be4b`.
Checksum và receipt: `dist/SHA256SUMS.txt`, `dist/release-manifest.json`.
EXE cũ và checksum/manifest được sao lưu trong
`.cache/previous-build-before-personal-2.1.2/`.

## Giới hạn

- GNT cá nhân chưa hỗ trợ vì chưa có lệnh tải được xác minh.
- Tab thông báo cá nhân dùng cổng cá nhân cũ; DVC hỗ trợ thông báo đính kèm
  tờ khai qua luồng tải hồ sơ. Lượt này không kiểm chứng live lại cổng cá nhân cũ.
- Kết quả online chỉ xác nhận tài khoản/kỳ và số tệp đã thử ở bảng trên.
- Build cục bộ, chưa phát hành lên GitHub. Smoke trên máy build không thay thế
  kiểm tra riêng trên máy Windows sạch.
