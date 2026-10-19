# Dung lượng Full 2.0 — 19/10/2026

| Build | EXE | OneDir | Startup trung vị | RAM idle |
|---|---:|---:|---:|---:|
| Baseline | 202,938,102 B | 410,887,557 B | 5.757 s | 167,301,120 B |
| Full 1.1 | 88,256,580 B | 223,618,350 B | 4.072 s | 168,087,552 B |
| Full 2.0 | **88,321,431 B** | **223,682,817 B** | **15.114 s** | **106,577,920 B** |

Giảm 56.48% EXE so với baseline. MB=10^6 B, MiB=2^20 B.
Giữ OCR tự động, đạt dưới 100 MB; chưa đạt dưới 80 MB. Không dùng UPX.
SHA-256: `17e10d910f50610b5406d5e13088c7d29036ee5fa2da8d44e6f790515ad51c06`.

Windows 11 x64, CPython 3.11.15, PyInstaller 6.22.3, Qt Essentials 6.8.3.
Runtime `.venv-release-1.1` tách khỏi ruff/mypy/psutil ở `.venv-review`.
Version resource 2.0.0.0, onefile/windowed; EXE chưa ký.
Đo ba tiến trình mới đến native window, RAM tổng parent/child sau 1 giây idle;
không xóa OS cache. Không khẳng định tốc độ trên máy sạch.

Các số startup 1.1/baseline là mốc đo trước, điều kiện cache/antivirus có thể khác.
So sánh workflow cùng lượt: 1.1 trung vị 15.737 s, 2.0 15.896 s; ba lần mỗi EXE,
cùng 15 declarations/5 MAPPED/PARTIAL. [Dữ liệu đo](desktop-evidence/2.0/workflow.json).

## Thành phần runtime

```text
[
  [
    "PySide6_Essentials",
    "6.8.3"
  ],
  [
    "altgraph",
    "0.17.5"
  ],
  [
    "beautifulsoup4",
    "4.15.0"
  ],
  [
    "certifi",
    "2026.10.18"
  ],
  [
    "charset-normalizer",
    "3.5.2"
  ],
  [
    "coloredlogs",
    "15.0.1"
  ],
  [
    "ddddocr",
    "1.6.1"
  ],
  [
    "et_xmlfile",
    "2.0.0"
  ],
  [
    "flatbuffers",
    "25.12.19"
  ],
  [
    "humanfriendly",
    "10.0"
  ],
  [
    "idna",
    "3.20"
  ],
  [
    "lxml",
    "6.1.3"
  ],
  [
    "mpmath",
    "1.3.0"
  ],
  [
    "numpy",
    "2.4.6"
  ],
  [
    "onnxruntime",
    "1.20.1"
  ],
  [
    "opencv-python",
    "4.11.0.86"
  ],
  [
    "openpyxl",
    "3.1.5"
  ],
  [
    "packaging",
    "26.3"
  ],
  [
    "pefile",
    "2024.8.26"
  ],
  [
    "pillow",
    "12.3.0"
  ],
  [
    "protobuf",
    "7.36.2"
  ],
  [
    "pyinstaller",
    "6.22.3"
  ],
  [
    "pyinstaller-hooks-contrib",
    "2026.8"
  ],
  [
    "pyreadline3",
    "3.5.6"
  ],
  [
    "pywin32-ctypes",
    "0.2.3"
  ],
  [
    "requests",
    "2.34.2"
  ],
  [
    "setuptools",
    "84.0.0"
  ],
  [
    "shiboken6",
    "6.8.3"
  ],
  [
    "soupsieve",
    "3.0.3"
  ],
  [
    "sympy",
    "1.14.0"
  ],
  [
    "tai-ho-so-thue-gtgt",
    "1.0.0"
  ],
  [
    "typing_extensions",
    "4.16.0"
  ],
  [
    "urllib3",
    "2.8.0"
  ]
]
```

## 30 entry lớn nhất trong archive

| Tệp | Nén B | Gốc B |
|---|---:|---:|
| `cv2\cv2.pyd` | 26,177,586 | 74,938,880 |
| `numpy.libs\libscipy_openblas64_-63c857e738469261263c764a36be9436.dll` | 6,428,148 | 20,415,488 |
| `onnxruntime\capi\onnxruntime_pybind11_state.pyd` | 5,509,084 | 15,845,408 |
| `ddddocr\common_old.onnx` | 6,773,170 | 13,606,051 |
| `onnxruntime\capi\onnxruntime.dll` | 4,922,898 | 13,557,800 |
| `PySide6\Qt6Gui.dll` | 4,071,856 | 9,285,768 |
| `PYZ.pyz` | 8,448,635 | 8,448,635 |
| `libcrypto-3-x64.dll` | 2,047,368 | 7,983,104 |
| `PySide6\Qt6Widgets.dll` | 2,975,608 | 6,500,488 |
| `PySide6\Qt6Core.dll` | 2,524,665 | 6,159,496 |
| `python311.dll` | 2,304,780 | 5,846,016 |
| `PySide6\QtWidgets.pyd` | 1,853,344 | 5,824,648 |
| `lxml\etree.cp311-win_amd64.pyd` | 2,028,492 | 4,049,920 |
| `PySide6\QtGui.pyd` | 1,422,508 | 3,992,200 |
| `numpy\_core\_multiarray_umath.cp311-win_amd64.pyd` | 1,215,204 | 3,703,296 |
| `PySide6\QtCore.pyd` | 1,248,895 | 3,442,824 |
| `PIL\_imaging.cp311-win_amd64.pyd` | 1,021,047 | 2,632,704 |
| `lxml\objectify.cp311-win_amd64.pyd` | 1,038,730 | 1,744,896 |
| `libssl-3-x64.dll` | 449,788 | 1,579,520 |
| `base_library.zip` | 413,043 | 1,443,233 |
| `unicodedata.pyd` | 408,839 | 1,128,960 |
| `PySide6\plugins\platforms\qwindows.dll` | 403,180 | 907,912 |
| `numpy\random\_generator.cp311-win_amd64.pyd` | 268,583 | 608,768 |
| `PySide6\plugins\imageformats\qjpeg.dll` | 195,052 | 575,624 |
| `numpy.libs\msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll` | 184,649 | 575,056 |
| `PySide6\MSVCP140.dll` | 182,662 | 565,384 |
| `shiboken6\MSVCP140.dll` | 182,657 | 565,384 |
| `numpy\random\mtrand.cp311-win_amd64.pyd` | 215,334 | 512,512 |
| `shiboken6\shiboken6.abi3.dll` | 180,726 | 371,848 |
| `lxml\html\_difflib.cp311-win_amd64.pyd` | 150,681 | 346,624 |

## Cắt gọt và kiểm chứng

Chỉ giữ model ddddocr mặc định `common_old.onnx`, Qt Core/GUI/Widgets,
qwindows/qico/qjpeg/style, cv2/ONNX CPU/numpy và HTTPS requests.
Loại model beta/detection, FFmpeg, Qt Quick/QML/PDF/Network/WebEngine,
translations và plugin không dùng. cv2 import ở top level của ddddocr nên giữ lại.
Không bundle test, dữ liệu thuế thật, `.env`, logs hoặc công cụ phát triển.

460 test tổng, 6 skip; ruff/mypy PASS. Native EXE 18 cấu hình và frozen offline/OCR
hai lượt PASS. Bản đồ nội tạng đầy đủ: [inventory](desktop-evidence/2.0/inventory.json).
[Phương pháp và giới hạn](DESKTOP_ACCEPTANCE.md).
