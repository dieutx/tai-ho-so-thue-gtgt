# Báo cáo dung lượng Full 1.1 — 19/10/2026

Số đo build Windows thực tế. MB = 10^6 B; MiB = 2^20 B.

| Build | EXE | OneDir thực | Startup trung vị | RAM idle trung vị |
|---|---:|---:|---:|---:|
| Baseline | 202,938,102 B = 202.94 MB (193.54 MiB) | 410,887,557 B = 410.89 MB (391.85 MiB) | 5.757 s | 167,301,120 B |
| Full 1.1 | **88,256,580 B = 88.26 MB (84.17 MiB)** | 223,618,350 B = 223.62 MB (213.26 MiB) | **4.072 s** | 168,087,552 B |

EXE giảm 56.51%; OneDir giảm
45.58%. Đạt mục tiêu <100 MB;
chưa đạt <80 MB. Full vẫn có OCR tự động, không phải bản Lite.

SHA-256:

```text
be8b860292caf5ef755a186db16da02870c5f3e7c1d7d51341abc89196a20a1a
```

## Môi trường và phương pháp

Windows 11 10.0.22631 x64; CPython 3.11.15; PyInstaller 6.22.3;
PySide6-Essentials 6.8.3; ddddocr 1.6.1; onnxruntime 1.20.1 CPU;
opencv-python 4.11.0.86. Onefile/windowed, version 1.1.0.0, icon, không UPX.

Venv runtime mới `.venv-release-1.1` chỉ cài `requirements-desktop.txt -e .`.
Ruff/mypy/psutil ở `.venv-review`, tách khỏi môi trường đóng gói. ORT 1.20.1 là
pin đã đo/kiểm thử cho bản slim này, không phải tuyên bố phiên bản duy nhất
cài được trên Python 3.11. Manifest runtime thực tế:

```text
PySide6_Essentials==6.8.3
altgraph==0.17.5
beautifulsoup4==4.15.0
certifi==2026.10.18
charset-normalizer==3.5.2
coloredlogs==15.0.1
ddddocr==1.6.1
et_xmlfile==2.0.0
flatbuffers==25.12.19
humanfriendly==10.0
idna==3.20
lxml==6.1.3
mpmath==1.3.0
numpy==2.4.6
onnxruntime==1.20.1
opencv-python==4.11.0.86
openpyxl==3.1.5
packaging==26.3
pefile==2024.8.26
pillow==12.3.0
protobuf==7.36.2
pyinstaller==6.22.3
pyinstaller-hooks-contrib==2026.8
pyreadline3==3.5.6
pywin32-ctypes==0.2.3
requests==2.34.2
setuptools==84.0.0
shiboken6==6.8.3
soupsieve==3.0.3
sympy==1.14.0
tai-ho-so-thue-gtgt==1.0.0
typing_extensions==4.16.0
urllib3==2.8.0
```

`scripts/size_inventory.py` đọc CArchive và quét toàn bộ OneDir được build
bằng chính spec với `TAIHOSOTHUE_ONEDIR=1`. Baseline là EXE gốc đã bảo quản
và OneDir build từ snapshot source. Bảng TOP 30 sắp theo byte giải nén; byte
nén được ghi riêng để tránh nhầm đóng góp vào EXE. Archive cuối có
160 entry, tổng 223,330,978 B giải nén.

Startup đo ba tiến trình mới, đồng hồ đến cửa sổ native đầu tiên. RAM là tổng
working set cha+con sau một giây idle. Không xóa cache OS; đây không phải đo
cold boot/VM sạch. Máy đo có 12 CPU logic, RAM 34.267.271.168 B.

| Lượt | Startup (s) | RAM idle (byte) |
|---:|---:|---:|
| 1 | 4.494 | 168,222,720 |
| 2 | 3.932 | 167,997,440 |
| 3 | 4.072 | 168,087,552 |

So sánh thời gian workflow trước/sau: NOT RUN. EXE baseline vượt timeout 180 giây ở lượt đầu; không có số đo hợp lệ để so sánh. Hai lượt frozen offline/OCR của bản 1.1 vẫn PASS với 15 bản ghi/5 MAPPED. Online trước/sau không có baseline cổng thật cùng thời điểm;
chỉ công bố thời gian tải thật bản hiện tại trong báo cáo nghiệm thu.

Lệnh tái lập:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1 -MeasureOnedir
.venv-release-tools/Scripts/python.exe scripts/benchmark_windows.py dist/TaiHoSoThue-Windows.exe --output .cache/optimization/release-1.1/performance.json
```

Khi dùng venv đã có, truyền `-Python`, `-ToolsPython`, `-SkipInstall`; hướng dẫn
ở [BUILD_WINDOWS.md](../BUILD_WINDOWS.md). Artifact đo chi tiết nằm trong
`.cache/optimization/release-1.1`; bản inventory/performance không nhạy cảm được
giữ ở [evidence 1.1](desktop-evidence/1.1/inventory.json).

## TOP 30 trước tối ưu

| # | Entry | Nén (byte) | Giải nén (byte) |
|---:|---|---:|---:|
| 1 | `cv2\cv2.pyd` | 30,688,864 | 86,293,504 |
| 2 | `ddddocr\common.onnx` | 50,299,571 | 54,088,400 |
| 3 | `cv2\opencv_videoio_ffmpeg500_64.dll` | 12,960,677 | 30,876,160 |
| 4 | `PySide6\opengl32sw.dll` | 7,660,518 | 20,639,880 |
| 5 | `numpy.libs\libscipy_openblas64_-63c857e738469261263c764a36be9436.dll` | 6,428,148 | 20,415,488 |
| 6 | `ddddocr\common_det.onnx` | 18,677,423 | 20,127,694 |
| 7 | `onnxruntime\capi\onnxruntime_pybind11_state.pyd` | 6,785,073 | 19,079,480 |
| 8 | `onnxruntime\capi\onnxruntime.dll` | 6,499,950 | 18,446,136 |
| 9 | `ddddocr\common_old.onnx` | 6,773,170 | 13,606,051 |
| 10 | `PySide6\Qt6Gui.dll` | 4,071,856 | 9,285,768 |
| 11 | `PYZ.pyz` | 8,134,610 | 8,134,610 |
| 12 | `libcrypto-3-x64.dll` | 2,047,368 | 7,983,104 |
| 13 | `PIL\_avif.cp311-win_amd64.pyd` | 4,321,271 | 7,888,896 |
| 14 | `PySide6\Qt6Widgets.dll` | 2,975,608 | 6,500,488 |
| 15 | `PySide6\Qt6Quick.dll` | 2,755,117 | 6,281,352 |
| 16 | `PySide6\Qt6Core.dll` | 2,524,665 | 6,159,496 |
| 17 | `python311.dll` | 2,304,780 | 5,846,016 |
| 18 | `PySide6\QtWidgets.pyd` | 1,853,344 | 5,824,648 |
| 19 | `PySide6\Qt6Pdf.dll` | 2,697,448 | 5,337,736 |
| 20 | `PySide6\Qt6Qml.dll` | 2,088,152 | 5,250,184 |
| 21 | `lxml\etree.cp311-win_amd64.pyd` | 2,028,492 | 4,049,920 |
| 22 | `PySide6\QtGui.pyd` | 1,422,508 | 3,992,200 |
| 23 | `numpy\_core\_multiarray_umath.cp311-win_amd64.pyd` | 1,215,204 | 3,703,296 |
| 24 | `PySide6\QtCore.pyd` | 1,248,895 | 3,442,824 |
| 25 | `PIL\_imaging.cp311-win_amd64.pyd` | 1,021,047 | 2,632,704 |
| 26 | `PySide6\Qt6OpenGL.dll` | 397,343 | 1,970,824 |
| 27 | `PySide6\Qt6Network.dll` | 773,087 | 1,755,784 |
| 28 | `lxml\objectify.cp311-win_amd64.pyd` | 1,038,730 | 1,744,896 |
| 29 | `libssl-3-x64.dll` | 449,788 | 1,579,520 |
| 30 | `base_library.zip` | 411,975 | 1,443,233 |

## TOP 30 sau tối ưu (1.1)

| # | Entry | Nén (byte) | Giải nén (byte) |
|---:|---|---:|---:|
| 1 | `cv2\cv2.pyd` | 26,177,586 | 74,938,880 |
| 2 | `numpy.libs\libscipy_openblas64_-63c857e738469261263c764a36be9436.dll` | 6,428,148 | 20,415,488 |
| 3 | `onnxruntime\capi\onnxruntime_pybind11_state.pyd` | 5,509,084 | 15,845,408 |
| 4 | `ddddocr\common_old.onnx` | 6,773,170 | 13,606,051 |
| 5 | `onnxruntime\capi\onnxruntime.dll` | 4,922,898 | 13,557,800 |
| 6 | `PySide6\Qt6Gui.dll` | 4,071,856 | 9,285,768 |
| 7 | `PYZ.pyz` | 8,384,168 | 8,384,168 |
| 8 | `libcrypto-3-x64.dll` | 2,047,368 | 7,983,104 |
| 9 | `PySide6\Qt6Widgets.dll` | 2,975,608 | 6,500,488 |
| 10 | `PySide6\Qt6Core.dll` | 2,524,665 | 6,159,496 |
| 11 | `python311.dll` | 2,304,780 | 5,846,016 |
| 12 | `PySide6\QtWidgets.pyd` | 1,853,344 | 5,824,648 |
| 13 | `lxml\etree.cp311-win_amd64.pyd` | 2,028,492 | 4,049,920 |
| 14 | `PySide6\QtGui.pyd` | 1,422,508 | 3,992,200 |
| 15 | `numpy\_core\_multiarray_umath.cp311-win_amd64.pyd` | 1,215,204 | 3,703,296 |
| 16 | `PySide6\QtCore.pyd` | 1,248,895 | 3,442,824 |
| 17 | `PIL\_imaging.cp311-win_amd64.pyd` | 1,021,047 | 2,632,704 |
| 18 | `lxml\objectify.cp311-win_amd64.pyd` | 1,038,730 | 1,744,896 |
| 19 | `libssl-3-x64.dll` | 449,788 | 1,579,520 |
| 20 | `base_library.zip` | 412,658 | 1,443,233 |
| 21 | `unicodedata.pyd` | 408,839 | 1,128,960 |
| 22 | `PySide6\plugins\platforms\qwindows.dll` | 403,180 | 907,912 |
| 23 | `numpy\random\_generator.cp311-win_amd64.pyd` | 268,583 | 608,768 |
| 24 | `PySide6\plugins\imageformats\qjpeg.dll` | 195,052 | 575,624 |
| 25 | `numpy.libs\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll` | 184,649 | 575,056 |
| 26 | `PySide6\MSVCP140.dll` | 182,662 | 565,384 |
| 27 | `shiboken6\MSVCP140.dll` | 182,657 | 565,384 |
| 28 | `numpy\random\mtrand.cp311-win_amd64.pyd` | 215,334 | 512,512 |
| 29 | `shiboken6\shiboken6.abi3.dll` | 180,726 | 371,848 |
| 30 | `lxml\html\_difflib.cp311-win_amd64.pyd` | 150,681 | 346,624 |

## Cắt gọt và giới hạn <80 MB

- Chỉ giữ model mặc định `common_old.onnx` (6.773.170 B nén). Loại model beta
  `common.onnx` (50.299.571 B nén) và detection (18.677.423 B nén): desktop luôn
  gọi `DdddOcr(beta=False)`, không có tùy chọn detection/beta.
- Loại FFmpeg video (~12,96 MB nén), Qt QML/Quick/Pdf/OpenGL/Network/Svg/
  VirtualKeyboard, opengl32sw (~7,66 MB), Qt translations và plugin không dùng.
  Giữ Qt Core/Gui/Widgets, qwindows/qico/qjpeg/style Windows và HTTPS requests.
- Loại Pillow AVIF/WebP không được luồng CAPTCHA dùng; giữ PNG/JPEG.
- cv2.pyd còn 26.177.586 B nén. ddddocr 1.6.1 import cv2 ở top level và lỗi
  nếu thiếu; bản headless đo riêng gần bằng kích thước nên không giúp đáng kể.
  Giữ ONNX CPU, numpy/OpenBLAS và model để OCR không cần mạng.
- OCR/native là phần lớn chi phí còn lại. Không dùng UPX hay bỏ OCR để đạt số.
  Chưa build Lite, không công bố kích thước Lite. EXE chưa ký Authenticode.

## Kiểm chứng

433 test (6 skip OCR tùy chọn), ruff PASS, mypy 65 module PASS; Qt offscreen
15 cấu hình và native frozen 15 cấu hình PASS. Frozen offline/OCR chạy hai lần
trong thư mục Unicode chỉ có EXE, socket bị chặn. Audit có 160
entry, 0 đường dẫn cấm, 0 secret khớp, 5 mapping JSON và 1 model ONNX.
Live: tải 5 hồ sơ DVC, 52 GNT, 5 thông báo; resume giữ hash. Chi tiết và các
giới hạn ở [nghiệm thu](DESKTOP_ACCEPTANCE.md).
VM Windows sạch và đổi DPI/màn hình vật lý: NOT RUN.
