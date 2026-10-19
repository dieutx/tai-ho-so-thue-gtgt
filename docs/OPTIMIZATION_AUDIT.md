# Audit nâng cấp session, compact UI và Full EXE — 19/10/2026

Nguồn sự thật là working tree local. Không checkout/ghi đè bằng GitLab. Baseline
được lưu trong `.cache/optimization/baseline`: EXE thật 202.938.102 byte
(202,94 MB / 193,54 MiB), snapshot allowlist `desktop`, `gdt_tax`, packaging,
LICENSE; không lấy `.env`, download, logs hoặc hồ sơ thật.

## Đường gọi và nguyên nhân login lặp

`desktop/main.py` → `ui.MainWindow.start` → `jobs.JobController/Worker` →
`services.run_online` → `Pipeline/GntPipeline/TbPipeline`. Mỗi lần run_online
tạo HttpClient mới và đóng trong finally. Mỗi pipeline tạo portal mới.
`EtaxLegacyPortal` giữ `_logged_in`, `dse_session_id`, `home_page_id` ở instance;
GntPortal/TbPortal kế thừa lớp này nhưng không chia sẻ instance/state nên vẫn
login mới. Dùng chung requests.Session đơn thuần cũng chưa đủ: phải giữ DSE/home
state, và reset form tra cứu theo operation. Comment cũ ở gnt/portal.py nói kế
thừa là dùng chung một lần login không đúng với orchestration trước nâng cấp.

UI thực tế chỉ có một cặp widget username/password chung, nhưng vẫn hiện form
này trong vùng cấu hình cả ba tab. `mode_changed` hiện xóa kết quả cũ. Header
chưa có account/session state; footer và subview làm bảng biến mất khi màn hình
thấp. Offline gọi hàm core trực tiếp, không login; phần này cần giữ nguyên.

## Build và thành phần nặng đã đo từ EXE

Entrypoint `packaging/entrypoint.py` → desktop.main. Spec thu toàn bộ data
ddddocr, collect_submodules(lxml), dynamic libs ONNX, Qt hooks mặc định. Venv
cũ `.venv-review` có dev extras và nhiều package; requirements-desktop chứa
`-e .[dev]`. Chưa có profile runtime sạch. Bản cũ không có torch/paddle/easyocr,
nhưng có cv2, FFmpeg, Qt Quick/QML/PDF và 3 model ONNX.

Các entry lớn theo kích thước **nén trong archive** (không nhầm với offset):

| Thành phần | Byte nén |
|---|---:|
| ddddocr/common.onnx (beta, không bật) | 50.299.571 |
| cv2/cv2.pyd | 30.688.864 |
| ddddocr/common_det.onnx (detection, không dùng) | 18.677.423 |
| cv2/opencv_videoio_ffmpeg500_64.dll | 12.960.677 |
| Qt opengl32sw.dll | 7.660.518 |
| ONNX pybind .pyd | 6.785.073 |
| ddddocr/common_old.onnx (mặc định, phải giữ) | 6.773.170 |
| ONNX runtime DLL | 6.499.950 |
| NumPy OpenBLAS | 6.428.148 |
| PIL AVIF .pyd | 4.321.271 |

Model mặc định được xác minh từ code ddddocr đã cài và
[upstream README](https://github.com/sml2h3/ddddocr): `common_old.onnx`.
ddddocr 1.6.1 import SlideEngine và color filter dùng cv2; không thể xóa cv2
theo phỏng đoán. Build cuối dùng opencv-python 4.11.0.86 đã đo và kiểm thử;
bản headless đo riêng không giúp giảm đáng kể kích thước cv2.pyd.
Hooks/data filter theo [PyInstaller hooks](https://www.pyinstaller.org/en/stable/hooks.html).

## Thực thi

1. Baseline onedir được build từ snapshot để đo top 30/unpacked. Manifest và
   package list do scripts/size_inventory.py xuất JSON, không bundle tooling.
2. Thêm shared LegacySessionState tùy chọn, ETaxSessionManager có lock, account
   version và client DVC riêng. Response auth hết hạn được nhận diện cụ thể;
   retry tối đa một lần, file đã commit được core reuse. CLI giữ default cũ.
3. Một account dialog, date/output chung; state riêng từng tab; bảng luôn còn
   chỗ ở màn hình thấp, footer phụ vào menu. Không lưu credential.
4. Venv `.venv-release-1.1` mới: runtime base + PySide6 Essentials + ddddocr/CPU ONNX
   + PyInstaller. Chỉ giữ model mặc định, plugins thực cần và kiểm chứng frozen.
   Không đổi framework, không bỏ OCR, không tải model ở lần mở đầu.

## Kết quả tối ưu ban đầu (desktop 1.0)

- EXE onefile: **202.938.102 → 88.136.033 byte** (−56,6%), vẫn có OCR tự động.
- OneDir: **410.887.557 → 223.147.429 byte** (−45,7%).
- `ddddocr` chỉ còn `common_old.onnx`; loại `common.onnx` (beta) và
  `common_det.onnx` (detection) vì desktop luôn dùng model mặc định.
- Loại FFmpeg video backend của cv2, `PIL._avif/_webp`, opengl32sw, Qt
  Quick/Qml/Pdf/OpenGL/Network/Svg/VirtualKeyboard, QML tooling, translations và
  plugin không dùng. Giữ `qwindows.dll`, `qico.dll`, style Windows, Qt
  Core/Gui/Widgets, cv2, ONNX runtime CPU và numpy.
- `requirements-desktop.txt` không còn `-e .[dev]`; pin runtime CPython 3.11
  (onnxruntime 1.20.1 là bản cài được cho 3.11). ruff/mypy/psutil chỉ là tooling,
  không được import vào app và audit xác nhận không có trong archive.
- `mypy gdt_tax` giữ PASS; desktop chưa được đưa vào phạm vi mypy của build.

Desktop 1.1 bổ sung xử lý lỗi thực tế, DVC mặc định bật, cập nhật theo nút bấm,
qjpeg và kiểm tra đủ 15 cấu hình. Runtime và tooling được cài ở hai venv riêng;
không suy diễn rằng ORT 1.20.1 là phiên bản duy nhất cài được trên Python 3.11.
Các số đo 1.0 phía trên được giữ làm lịch sử; số đo 1.1 ở báo cáo bên dưới.

Số đo chi tiết, TOP 30 trước/sau, startup/RAM, kiểm chứng và lý do không xuống
< 80 MB ở [BUILD_SIZE_REPORT.md](BUILD_SIZE_REPORT.md). Kết quả test/UI/frozen
ở [DESKTOP_ACCEPTANCE.md](DESKTOP_ACCEPTANCE.md).
