"""Điểm vào cho bản ``.exe`` đóng gói bằng PyInstaller.

Bản EXE chỉ là bản thử nghiệm do CI tạo (job artifact), không phải bản release.
"""

from __future__ import annotations

import sys

from gdt_tax.cli import main

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")

if __name__ == "__main__":
    raise SystemExit(main())
