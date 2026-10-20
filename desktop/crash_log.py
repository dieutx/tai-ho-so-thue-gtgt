"""Bounded private native crash output and value-free Python exception frames."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from gdt_tax.redaction import exception_summary

_stream = None


def install_crash_log() -> None:
    global _stream
    if not getattr(sys, "frozen", False) or _stream is not None:
        return
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TaiHoSoThue" / "PRIVATE"
    try:
        root.mkdir(parents=True, exist_ok=True)
        target = root / "crash.log"
        if target.exists() and target.stat().st_size > 1024 * 1024:
            target.replace(root / "crash.previous.log")
        for path in root.glob("crash*.log"):
            if datetime.now().timestamp() - path.stat().st_mtime > 7 * 86400:
                path.unlink()
        _stream = target.open("a", encoding="utf-8", buffering=1)
    except OSError:
        return

    def excepthook(exc_type, exc, tb):
        if _stream is not None:
            _stream.write(f"\n[{datetime.now().isoformat()}] unhandled exception\n"
                          + exception_summary(exc_type, exc, tb) + "\n")
    sys.excepthook = excepthook
    try:
        import faulthandler
        faulthandler.enable(file=_stream, all_threads=True)
    except (ImportError, OSError):
        pass
