# One-file, windowed. Assets are allowlisted; user directories are never collected.
#
# Size policy (see docs/BUILD_SIZE_REPORT.md):
#   - ddddocr ships three ONNX models. Desktop only constructs DdddOcr(beta=False),
#     i.e. common_old.onnx, so the beta/detection models are excluded.
#   - cv2 is imported by ddddocr at package import; it stays. Video decoding is not
#     used by the CAPTCHA path, so the bundled FFmpeg video backend is dropped.
#   - Qt is Widgets-only. QML/Quick/PDF/OpenGL/SVG/VirtualKeyboard, QML tooling and
#     translations are not referenced by the application and are filtered after
#     Analysis. qwindows/qico/qjpeg/qmodernwindowsstyle remain for the native UI.
#   - Pillow AVIF/WebP decoders are unused (CAPTCHA inputs are PNG/JPEG).
from pathlib import Path
from importlib.metadata import PackageNotFoundError, distribution
import fnmatch
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

root = Path(SPECPATH).parent

# Only the default OCR model is loaded by the desktop solver. Keep charsets.py in
# the PYZ (it is a module, not data); the other models are optional beta/detection.
_OCR_DATA = {"common_old.onnx"}
ddddocr_data = [(src, dest) for src, dest in collect_data_files("ddddocr")
                if Path(src).name in _OCR_DATA]

datas = [(str(root / "gdt_tax" / "form_mappings" / "*.json"), "gdt_tax/form_mappings"),
         (str(root / "desktop" / "resources" / "app.ico"), "desktop/resources"),
         (str(root / "desktop" / "resources" / "release.json"), "desktop/resources"),
         (str(root / "LICENSE"), "licenses")]
datas += ddddocr_data
for package in ["PySide6", "PySide6-Essentials", "shiboken6", "ddddocr", "onnxruntime", "Pillow", "pypdf"]:
    try:
        dist = distribution(package)
    except PackageNotFoundError:
        continue  # PySide6 (full) is not installed; PySide6-Essentials is enough.
    for file in dist.files or []:
        if "license" in str(file).lower() or "copying" in str(file).lower():
            source = Path(dist.locate_file(file))
            if source.is_file():
                datas.append((str(source), "licenses/" + package + "/" + str(file.parent)))
binaries = collect_dynamic_libs("onnxruntime")
hidden = collect_submodules("lxml") + ["gdt_tax.captcha.ddddocr_solver", "openpyxl.cell._writer"]
a = Analysis([str(root / "packaging" / "entrypoint.py")], pathex=[str(root)],
             binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=["torch", "tensorflow", "paddle", "paddleocr", "easyocr", "PyQt5", "PyQt6",
                       "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
                       "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtPdf",
                       "PySide6.QtSvg", "PySide6.QtNetwork", "PySide6.QtOpenGL",
                       "PySide6.QtVirtualKeyboard", "PIL._avif", "PIL._webp",
                       "matplotlib", "scipy", "IPython", "pytest"],
             noarchive=False)

# Destinations are frozen paths such as "PySide6/Qt6Qml.dll" or
# "PySide6/plugins/imageformats/qwebp.dll". Every pattern below is justified by a
# feature the app never uses; native UI smoke (Qt windows + 18 DPI cases) and the
# frozen OCR/offline self-test are the regression gate.

def keep(entry):
    dest = str(entry[0]).replace("\\", "/")
    return not any(fnmatch.fnmatch(dest, pattern) for pattern in DROP)

DROP = [
    # Video/AVIF decoders are unreachable from the CAPTCHA and report paths.
    "cv2/opencv_videoio_ffmpeg*.dll",
    "PIL/_avif*",
    "PIL/_webp*",
    # Qt modules not imported by the Widgets UI. Qt6Network is kept out of the UI;
    # requests performs HTTPS, not QtNetwork.
    "PySide6/Qt6Qml*",
    "PySide6/Qt6Quick*",
    "PySide6/Qt6Pdf.dll",
    "PySide6/Qt6Designer*.dll",
    "PySide6/Qt6OpenGL.dll",
    "PySide6/Qt6Svg.dll",
    "PySide6/Qt6VirtualKeyboard.dll",
    "PySide6/Qt6Network.dll",
    "PySide6/QtOpenGL.pyd",
    "PySide6/QtSvg.pyd",
    "PySide6/QtQml*.pyd",
    "PySide6/QtQuick*.pyd",
    "PySide6/QtPdf.pyd",
    "PySide6/QtNetwork.pyd",
    "PySide6/QtVirtualKeyboard.pyd",
    # Software OpenGL fallback: Widgets renders with the raster engine/D3D11.
    "PySide6/opengl32sw.dll",
    # Qt translations are for Qt's own dialogs; app copy is Vietnamese. Keeps
    # English fallback for native button labels if a translation is missing.
    "PySide6/translations/*",
    # Plugins for formats/features the app does not open.
    "PySide6/plugins/qmltooling/*",
    "PySide6/plugins/sqldrivers/*",
    "PySide6/plugins/platforminputcontexts/*",
    "PySide6/plugins/networkinformation/*",
    "PySide6/plugins/generic/*",
    "PySide6/plugins/tls/*",
    "PySide6/plugins/iconengines/*",
    "PySide6/plugins/imageformats/qgif.dll",
    "PySide6/plugins/imageformats/qicns.dll",
    "PySide6/plugins/imageformats/qpdf.dll",
    "PySide6/plugins/imageformats/qsvg.dll",
    "PySide6/plugins/imageformats/qtga.dll",
    "PySide6/plugins/imageformats/qtiff.dll",
    "PySide6/plugins/imageformats/qwbmp.dll",
    "PySide6/plugins/imageformats/qwebp.dll",
    "PySide6/plugins/platforms/qdirect2d.dll",
    "PySide6/plugins/platforms/qminimal.dll",
    "PySide6/plugins/platforms/qoffscreen.dll",
]

a.binaries = [entry for entry in a.binaries if keep(entry)]
a.datas = [entry for entry in a.datas if keep(entry)]

pyz = PYZ(a.pure)
common = dict(name="TaiHoSoThue-Windows", debug=False, bootloader_ignore_signals=False,
              strip=False, upx=False, console=False, disable_windowed_traceback=False,
              icon=str(root / "desktop" / "resources" / "app.ico"),
              version=str(root / "packaging" / "version.txt"), uac_admin=False)
if os.environ.get("TAIHOSOTHUE_ONEDIR"):
    # Measurement/QA build only; release remains one-file below.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                   name="TaiHoSoThue-Windows")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)
