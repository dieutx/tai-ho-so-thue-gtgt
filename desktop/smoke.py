"""Explicit diagnostic entrypoints; no fixture/business data bundled in release."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from desktop import __version__
from gdt_tax.captcha.ddddocr_solver import DdddOcrSolver
from gdt_tax.errors import CaptchaError, PortalVerificationError
from gdt_tax.parser.registry import load_registry
from gdt_tax.run_hooks import RunHooks
from gdt_tax.verification import raise_for_portal_verification

from .services import RunConfig, run_offline


def captcha_retry_check() -> bool:
    """Exercise the frozen GUI solver offline, including rejected manual fallback."""
    from .jobs import GuiCaptchaSolver
    requests = []
    def manual(request):
        requests.append(request)
        request.respond('AB123')
    solver = GuiCaptchaSolver(RunHooks(), manual, use_ocr=False)
    solver.ocr = Mock()
    solver.ocr.solve.return_value = 'AB123'
    try:
        for _ in range(5):
            solver.solve(b'offline-fixture')
            solver.rejected()
        solver.solve(b'offline-fixture')
        try:
            solver.rejected()
        except CaptchaError:
            pass
        else:
            raise AssertionError('Rejected manual fallback did not stop the task')
        if len(requests) != 1 or solver.ocr.solve.call_count != 5:
            raise AssertionError('Automatic/manual CAPTCHA retry budget changed')
        solver.accepted()
        if solver.solve(b'offline-fixture') != 'AB123' or len(requests) != 1:
            raise AssertionError('Successful CAPTCHA did not reset the automatic solver')
        return True
    finally:
        solver.close()


def saved_accounts_check() -> bool:
    """Native vault roundtrip with fresh synthetic identities; always clean up."""
    from uuid import uuid4

    from PySide6.QtWidgets import QApplication

    from .account_dialog import AccountDialog
    from .account_store import AccountStore
    application = QApplication.instance() or QApplication([])
    store = AccountStore()
    names = ['smoke-' + uuid4().hex, 'smoke-' + uuid4().hex]
    try:
        for index, name in enumerate(names):
            store.save(name, 'synthetic-' + str(index) + '-đ')
        if not set(names).issubset(store.accounts()):
            raise AssertionError('Saved account enumeration failed')
        dialog = AccountDialog(username=names[0], store=store)
        try:
            if dialog.password.text() != 'synthetic-0-đ':
                raise AssertionError('Saved account password was not restored')
            dialog.accounts.setCurrentText(names[1])
            if dialog.password.text() != 'synthetic-1-đ':
                raise AssertionError('Saved account switching failed')
            dialog.accounts.setEditText('unsaved-synthetic-' + uuid4().hex)
            if dialog.password.text():
                raise AssertionError('Password retained after account edit')
            dialog.reject()
        finally:
            dialog.deleteLater()
            application.processEvents()
        store.save(names[0], 'synthetic-updated')
        if store.password(names[0]) != 'synthetic-updated':
            raise AssertionError('Saved password update failed')
    finally:
        for name in names:
            store.forget(name)
    if any(store.password(name) is not None for name in names):
        raise AssertionError('Synthetic credentials were not deleted')
    return True


def self_test(source: Path, output: Path, report: Path) -> int:
    result = {"version": __version__, "frozen": bool(getattr(__import__("sys"), "frozen", False))}
    metadata = json.loads((Path(__file__).parent / 'resources/release.json').read_text(encoding='utf-8'))
    result['source_sha'] = metadata.get('source_sha', '')
    result['core_version'] = metadata.get('core_version', '1.0.0')
    result['release_version'] = metadata.get('version', '')
    try:
        if result['release_version'] != __version__:
            raise AssertionError('Release metadata version differs from application')
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
                charset = ocr._get_ocr().get_charset()
                result['ocr_charset_sha256'] = hashlib.sha256(json.dumps(charset, ensure_ascii=True).encode('utf-8')).hexdigest()
                result['ocr_providers'] = ocr._get_ocr().get_model_info()['ocr_model']['providers']
            finally:
                ocr.close()
            result['captcha_fallback_bounded'] = captcha_retry_check()
            from .portal_checks import portal_regression_check
            result['portal_regressions'] = portal_regression_check()
            from gdt_tax.identity import account_fingerprint
            from gdt_tax.local_catalog import LocalCatalog
            from gdt_tax.models import CaseRecord
            owner = account_fingerprint('synthetic-frozen-catalog')
            catalog = LocalCatalog(output / 'persistent-smoke', owner)
            catalog.upsert_documents('tax', [CaseRecord('old', 'DVC', account_key=owner, ngay_nop='01/06/2025').to_dict(),
                                             CaseRecord('new', 'DVC', account_key=owner, ngay_nop='01/10/2026').to_dict()])
            catalog = LocalCatalog(output / 'persistent-smoke', owner)
            if (catalog.get_counts('tax')['total'] != 2
                    or len(catalog.get_documents('tax', '01/06/2025', '30/06/2025')) != 1
                    or len(catalog.get_documents('tax', '01/10/2026', '31/10/2026')) != 1
                    or catalog.integrity_check() != 'ok'):
                raise AssertionError('Persistent catalog multi-year/reopen contract failed')
            result['persistent_catalog'] = True
            from gdt_tax.table_contracts import TABLE_CONTRACT_VERSION
            result['schema_contract_version'] = TABLE_CONTRACT_VERSION
            if os.name == 'nt':
                result['saved_accounts_native'] = saved_accounts_check()
            challenge = ('<apm_do_not_touch></apm_do_not_touch><body>human visitor'
                         '<input name="answer" id="ans"><button id="jar">Submit</button></body>')
            try:
                raise_for_portal_verification(SimpleNamespace(content=challenge.encode(), text=challenge))
            except PortalVerificationError:
                result['portal_verification_detected'] = True
            else:
                raise AssertionError('Access verification page was not detected')
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
