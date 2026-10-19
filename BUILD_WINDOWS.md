# Tải Hồ Sơ Thuế — Windows desktop

Chạy bản phát hành: mở `dist/TaiHoSoThue-Windows.exe`. Một file, Windows x64,
không cần cài Python, Qt, pip hoặc Excel. Mở workbook cần ứng dụng đọc XLSX;
việc tạo workbook không cần Excel. Đây là phần mềm bên thứ ba.

Bản Full 2.0 onefile/windowed, giữ CAPTCHA tự
động ddddocr. Số đo, thành phần bị loại và lý do ở
[docs/BUILD_SIZE_REPORT.md](docs/BUILD_SIZE_REPORT.md).

## Build

Máy build cần Windows x64, CPython 3.11 x64 và Internet để cài dependency:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

Script tạo `.venv-release`, cài `requirements-desktop.txt` (runtime + Qt +
ddddocr/ONNX + PyInstaller, không có dev extras hay solver khác). Công cụ ruff/mypy
nằm trong `.venv-release-tools` từ `requirements-build-tools.txt`. Script chạy unittest,
ruff, mypy cho core, tạo metadata phiên bản, build spec, audit rồi smoke-test chính EXE.
Mỗi lệnh lỗi đều dừng build. Không xóa dữ liệu người dùng hoặc toàn bộ dist.
`dist` dành riêng cho executable phát hành; bằng chứng test ở `.cache`.

Pin trong `requirements-desktop.txt` dành cho CPython 3.11 x64; onnxruntime
1.20.1 là bản Windows cài được cho interpreter này. Đổi Python cần đo lại pin và
dung lượng, không chỉ sửa số version.

Có thể dùng Python 3.11 đã có đủ dependency:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -Python .venv-release-1.1/Scripts/python.exe -ToolsPython .venv-review/Scripts/python.exe -SkipInstall -MeasureOnedir
```

Phát triển:

```powershell
python -m pip install -r requirements-desktop.txt
python -m desktop.main
python scripts/check_ui.py
```

PyInstaller tự giải nén Qt, OCR và mapping vào thư mục tạm `_MEI...` lúc chạy,
vì vậy onefile khởi động chậm hơn dạng folder. Ứng dụng không ghi dữ liệu nghiệp
vụ vào bundle hoặc cạnh EXE. Cấu hình chỉ gồm trường cho phép, có schema 1,
lưu ở `%LOCALAPPDATA%\TaiHoSoThue\settings.json`; schema mới hơn không bị ghi đè.
Mật khẩu, tài khoản, proxy và header chỉ có trong phiên. Lựa chọn bật DVC được lưu,
mặc định bật trên desktop. Output mặc định lấy Documents từ Windows Known Folder
registry; nếu Documents chuyển vào OneDrive, ưu tiên `%LOCALAPPDATA%\TaiHoSoThue\HoSo`
để tránh xung đột đồng bộ. Thay nơi lưu bằng nút `Thay đổi`; đường dẫn đã chọn được tôn trọng.

Spec allowlist chỉ lấy code, JSON mapping, icon, model mặc định
`common_old.onnx`, native runtime và giấy phép. Hai model beta/detection của
ddddocr bị loại vì desktop luôn tạo `DdddOcr(beta=False)`. Qt hooks giữ
`qwindows.dll`, `qico.dll`, `qjpeg.dll`, style Windows và Qt Core/Gui/Widgets; QML/Quick/PDF/
OpenGL/Network/SVG/VirtualKeyboard, translations và plugin không dùng bị lọc.
Không gộp easyocr, paddleocr, torch hoặc WebEngine; không lấy `.env`, hồ sơ thật,
download hoặc log. Phiên bản build đã kiểm chứng được pin trong
requirements-desktop.txt.

Đo onedir để audit nội tạng mà không phát hành (spec dùng biến môi trường):

```powershell
$env:TAIHOSOTHUE_ONEDIR='1'
python -m PyInstaller --noconfirm --clean `
  --distpath .cache/optimization/onedir-dist `
  --workpath .cache/optimization/onedir-build packaging/TaiHoSoThue.spec
Remove-Item Env:TAIHOSOTHUE_ONEDIR
python scripts/size_inventory.py `
  .cache/optimization/onedir-dist/TaiHoSoThue-Windows/TaiHoSoThue-Windows.exe `
  --folder .cache/optimization/onedir-dist/TaiHoSoThue-Windows `
  --output .cache/optimization/onedir-inventory.json
```

Tham khảo cơ chế [PyInstaller spec/onefile](https://pyinstaller.org/en/stable/spec-files.html)
và [Qt for Python deployment](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html).
EXE chưa ký Authenticode; SmartScreen có thể cảnh báo. Không có chứng chỉ giả.

## Smoke và kiểm tra trên máy sạch

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke_test_windows.ps1
Get-FileHash dist/TaiHoSoThue-Windows.exe -Algorithm SHA256
```

Smoke copy EXE vào một thư mục Unicode chỉ có EXE, chạy pipeline offline hai
lần trên fixture repo, chặn socket trong self-test, nạp mapping và OCR từ bundle,
mở/đóng GUI, chụp/kiểm tra các vùng điều khiển với Windows Qt backend ở 18 cấu
hình: sáu kích thước 1920×1080, 1366×768, 1280×720, 1080×700, 1024×768, 1024×600,
mỗi kích thước ở 100/125/150%. Smoke không đăng nhập hoặc gọi cổng thuế.
Fixture không nằm trong EXE. Ảnh/check JSON/report lưu trong `.cache/smoke-<id>`.

Để kiểm chứng môi trường sạch, copy **duy nhất EXE** sang Windows 10/11 x64
chưa có Python/Qt/Excel; mở ứng dụng khi tắt mạng, chọn thư mục XML/ZIP thử và
chạy Offline. Kiểm tra Manual CAPTCHA bằng cấu hình manual khi thực hiện một
phiên tra cứu được phép. Kiểm tra Windows 10 riêng, RDP và đổi màn hình vật lý
cần máy/phiên tương ứng; không suy ra đã PASS từ máy build.

## Sử dụng và giới hạn

- Bốn nghiệp vụ dùng chung nơi lưu; offline có nguồn riêng, không cần tài khoản.
- `Tra cứu` đăng nhập và đọc danh sách, không tạo catalog/báo cáo hoặc tải ZIP/XML/PDF. Tải đã chọn giữ đúng tài khoản, kỳ và nơi lưu của lần tra cứu.
- Desktop bật DVC mặc định, có thể tắt trong Cài đặt. Khi tắt, phạm vi sau cutoff
  báo thiếu. CLI giữ mặc định cũ. DVC dùng cookie riêng, GNT/TB dùng legacy toàn khoảng.
- Nhấp đúp hoặc menu phải để xem metadata đầy đủ; menu phải mở file đã tồn tại.
- `Dừng an toàn` đợi request/inference hoặc ghi file hiện tại kết thúc; request
  đang gửi chịu timeout cấu hình. Retry/pause/CAPTCHA chờ có thể hủy. Không kill thread.
- `Ctrl+O` mở nơi lưu; `Ctrl+L` xem log; `Ctrl+Enter` bắt đầu. Log có bộ lọc và
  sao chép, giữ tối đa 5.000 dòng đã ẩn bí mật.
- Offline chạy Kiểm kê → Đọc XML → Phân loại → Xuất Excel. Khi chạy riêng một
  bước, dùng cùng thư mục kết quả; thiếu dependency hoặc manifest khác nguồn báo lỗi.
- Kết quả `NEED_MAPPING`/`UNKNOWN`/`CONFLICT` giữ nguyên và hiển thị chưa đầy đủ.
  Parser không tính lại thuế, cộng các lần nộp, parse chỉ tiêu GNT hay nội dung PDF.
- Chỉ dùng output riêng từng tài khoản. Giới hạn định danh/gộp metadata của core
  ghi trong REVIEW vẫn áp dụng. Kết quả tải thật được ghi trong báo cáo nghiệm thu.
- Danh mục đầu ra có thể gộp lịch sử theo core; bảng UI chỉ hiển thị job hiện tại.
- Nhấn `v2.0.0` để xem thay đổi và kiểm tra bản mới. Chỉ khi bấm nút kiểm tra,
  app mới đọc GitLab public releases; không gửi tài khoản thuế, không tự cài.
  Repo riêng tư/chưa có release sẽ được thông báo rõ, không báo giả có cập nhật.
- Menu `Tệp & nhật ký` có tải nhiều nhóm tuần tự và mở/chuyển dữ liệu cũ.
  Tệp hợp lệ được dùng lại; màu sắc và nhãn chữ thể hiện thao tác/trạng thái.

Kết quả thực chạy và SHA-256 của bản bàn giao ghi ở `docs/DESKTOP_ACCEPTANCE.md`;
số đo dung lượng ở `docs/BUILD_SIZE_REPORT.md`.

## Phát hành GitLab

Sau khi build và kiểm chứng, commit/push mã nguồn và tag `desktop-vX.Y.Z`.
Token API được lưu riêng trong Windows Credential Manager với tên
`TaiHoSoThue:GitLabReleaseApi:gitlab.com`; không thay OAuth đang dùng cho Git.
Các lần phát hành sau trên cùng tài khoản Windows tự đọc lại credential này.
Ngoài Windows có thể truyền `GITLAB_TOKEN` qua môi trường, không đặt vào argv/repo.

```powershell
python scripts/release_gitlab.py check
python scripts/release_gitlab.py publish --tag desktop-v2.0.0 --notes .cache/optimization/release-notes-2.0.md
python scripts/release_gitlab.py verify --tag desktop-v2.0.0
```

Thay asset trong cùng phiên bản (chỉ khi được yêu cầu):

```powershell
python scripts/release_gitlab.py replace --tag desktop-v2.0.0 --notes .cache/optimization/release-notes-2.0.md
```

Lệnh `replace` giữ nguyên Release/link ID/link tải công khai, upload tệp có hash
trong tên nội bộ để tránh cache, cập nhật URL asset/checksum và tải lại xác minh.

Chuẩn bị `dist/SHA256SUMS.txt` cùng EXE trước publish. Helper upload Generic Package,
tạo Release có link EXE/checksum và tải lại để đối chiếu SHA-256/kích thước.
README dùng permalink latest để giữ link tải khi có phiên bản mới.
Không lưu token vào mã nguồn, nhật ký hoặc asset phát hành.
