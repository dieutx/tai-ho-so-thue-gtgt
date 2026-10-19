"""Explicit diagnostic entrypoints; no fixture/business data bundled in release."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
from pathlib import Path
from unittest.mock import patch

from desktop import __version__
from gdt_tax.captcha.ddddocr_solver import DdddOcrSolver
from gdt_tax.parser.registry import load_registry
from gdt_tax.run_hooks import RunHooks

from .services import RunConfig, run_offline


def self_test(source: Path, output: Path, report: Path) -> int:
    result = {"version": __version__, "frozen": bool(getattr(__import__("sys"), "frozen", False))}
    try:
        def no_network(*_args, **_kwargs):
            raise AssertionError("Network accessed by offline smoke test")
        with patch.object(socket.socket, "connect", no_network), patch.object(socket, "create_connection", no_network):
            config = RunConfig("offline", output, source=source)
            config.validate()
            job = run_offline(config, RunHooks(), logging.getLogger("gdt_tax.smoke"))
            if not job.rows or not (output / "Tax_Return_Summary.xlsx").is_file():
                raise AssertionError("Offline fixture pipeline produced no workbook/rows")
            result.update(state=job.state, declarations=len(job.rows), mapped=sum(r.get("status") == "MAPPED" for r in job.rows))
            if load_registry().lookup("892", "2.9.4") is None:
                raise AssertionError("Bundled form mappings missing")
            ocr = DdddOcrSolver(require_length=False)
            try:
                text = ocr.solve((source / "sample_captcha.png").read_bytes())
                if not text:
                    raise AssertionError("OCR returned empty output")
                result["ocr_offline"] = True
                import ddddocr
                result["ocr_fixture_sha256"] = hashlib.sha256((source / "sample_captcha.png").read_bytes()).hexdigest()
                result["ocr_text_sha256"] = hashlib.sha256(text.encode('utf-8')).hexdigest()
                result["ocr_model_sha256"] = hashlib.sha256((Path(ddddocr.__file__).parent / "common_old.onnx").read_bytes()).hexdigest()
            finally:
                ocr.close()
        result["pass"] = True
        code = 0
    except Exception as error:
        result.update({"pass": False, "error": f"{type(error).__name__}: {error}"})
        code = 1
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


def ui_check(application, window, output: Path, size: str) -> None:
    from types import SimpleNamespace

    from PySide6.QtCore import QDate, QRect
    from PySide6.QtWidgets import QScrollArea
    physical_w, physical_h = map(int, size.split("x"))
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    width, height = int(physical_w / scale), int(physical_h / scale)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    window.resize(width, height)
    window.to_date.setDate(QDate(2026, 10, 19))
    application.processEvents()
    available = QRect(0, 0, width, height)
    with patch.object(window, "screen", return_value=SimpleNamespace(availableGeometry=lambda: available)):
        window.fit_screen()
    application.processEvents()
    for index, name in enumerate(["tax", "gnt", "notice", "offline"]):
        window.tabs.setCurrentIndex(index)
        application.processEvents()
        controls = [window.start_button, window.stop_button, window.output, window.table, window.menu_button,
                    window.input_path if name == "offline" else window.from_date,
                    window.tabs if window.tabs.isVisible() else window.navigation]
        for control in controls:
            rect = control.rect()
            top_left = control.mapTo(window, rect.topLeft())
            bottom_right = control.mapTo(window, rect.bottomRight())
            if not window.rect().contains(top_left) or not window.rect().contains(bottom_right):
                errors.append(f"{name}: clipped {control.objectName() or type(control).__name__}")
            if not control.isVisible():
                errors.append(f"{name}: hidden required control {type(control).__name__}")
        if window.findChildren(QScrollArea):
            errors.append("Outer scroll area found")
        if window.width() > width or window.height() > height:
            errors.append(f"{name}: minimum size exceeded requested size {width}x{height}; actual {window.width()}x{window.height()}")
        if not available.contains(window.frameGeometry()):
            errors.append(f"{name}: frame outside simulated workarea")
        window.grab().save(str(output / f"{name}-{physical_w}x{physical_h}-{scale}.png"))
    (output / f"check-{physical_w}x{physical_h}-{scale}.json").write_text(json.dumps({"pass": not errors, "logical_workarea": [width, height], "client_size": [window.width(), window.height()], "errors": errors}, indent=2), encoding="utf-8")
    window.close()
    application.exit(1 if errors else 0)
