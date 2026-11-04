"""Desktop parity, cancellation, security and Qt lifecycle with existing fixtures."""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from desktop.services import RunConfig, run_offline, run_online
from desktop.settings_store import Preferences, SettingsStore
from gdt_tax import classify, export, inventory
from gdt_tax.cli import main as tax_cli
from gdt_tax.gnt.cli import main as gnt_cli
from gdt_tax.parser.cli import main as parse_cli
from gdt_tax.run_hooks import RunCancelled, RunHooks
from gdt_tax.tb.cli import main as tb_cli
from tests.support import FakeHttp, StubCaptcha, cleanup_temporary_directory
from tests.test_etax_legacy import make_legacy_handler
from tests.test_gnt import make_gnt_handler
from tests.test_tb import make_tb_handler

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

    from desktop.jobs import CaptchaRequest, GuiCaptchaSolver, JobController, Redactor
    from desktop.ui import AdvancedDialog, MainWindow
    HAS_QT = True
except ImportError:
    HAS_QT = False

FIXTURES = Path(__file__).parent / "fixtures"


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.prefs = Preferences(record_delay=0.0, page_delay=0.0, jitter=0.0, login_attempts=1, search_attempts=1)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def config(self, mode="tax", **kwargs):
        values = dict(mode=mode, output=self.root / mode, username="synthetic-taxpayer-QL", password="fixture-password", preferences=self.prefs)
        values.update(kwargs)
        return RunConfig(**values)

    def test_all_three_online_adapters_match_cli_outputs_and_dry_run(self):
        cases = [("tax", tax_cli, "gdt_tax.cli", make_legacy_handler, "danh_sach_ho_so.json", ".zip"),
                 ("gnt", gnt_cli, "gdt_tax.gnt.cli", make_gnt_handler, "danh_sach_giay_nop_tien.json", ".xml"),
                 ("notice", tb_cli, "gdt_tax.tb.cli", make_tb_handler, "danh_sach_thong_bao.json", ".pdf")]
        for mode, cli, module, factory, metadata, suffix in cases:
            with self.subTest(mode=mode):
                config = self.config(mode)
                config.validate()
                result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger("gdt_tax.test"), http=FakeHttp(factory({})))
                self.assertEqual(result.state, "SUCCESS")
                self.assertGreater(result.downloaded, 0)
                cli_output = self.root / (mode + "-cli")
                settings = replace(config.settings(), download_dir=cli_output)
                with patch(module + ".Settings.from_env", return_value=settings), patch(module + ".create_solver", return_value=StubCaptcha()), patch(module + ".HttpClient", return_value=FakeHttp(factory({}))):
                    self.assertEqual(cli(["--env-file", str(self.root / "missing.env")]), 0)
                desktop_rows = json.loads((config.output / metadata).read_text(encoding="utf-8"))
                cli_rows = json.loads((cli_output / metadata).read_text(encoding="utf-8"))
                # Each independent query records its actual observation time.
                for rows in (desktop_rows, cli_rows):
                    for row in rows:
                        row.pop('trang_thai_cap_nhat', None)
                self.assertEqual(desktop_rows, cli_rows)
                dry = replace(config, output=self.root / (mode + "-dry"), dry_run=True)
                dry.validate()
                lookup = run_online(dry, RunHooks(), StubCaptcha(), logging.getLogger("gdt_tax.test"), http=FakeHttp(factory({})))
                self.assertEqual(lookup.state, "SUCCESS")
                self.assertEqual(lookup.downloaded, 0)
                self.assertFalse(list(dry.output.glob("*" + suffix)))
                # Post-cutoff GNT/TB still query legacy.
                if mode != "tax":
                    after = replace(config, from_date="01/08/2026", to_date="31/08/2026")
                    outcome = run_online(after, RunHooks(), StubCaptcha(), logging.getLogger("gdt_tax.test"), http=FakeHttp(factory({})))
                    self.assertEqual(outcome.state, "SUCCESS")

    def test_dvc_disabled_is_partial_even_with_no_records(self):
        config = self.config(from_date="01/07/2025", to_date="31/07/2025", dry_run=True)
        config.validate()
        http = FakeHttp(lambda *_args: self.fail("DVC made network request"))
        result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger("gdt_tax.test"), http=http)
        self.assertEqual(result.state, "PARTIAL")
        self.assertEqual(result.skipped, 1)

    def test_stop_after_record_flushes_metadata_and_preserves_file(self):
        for mode, factory, metadata in [("tax", make_legacy_handler, "danh_sach_ho_so.json"), ("gnt", make_gnt_handler, "danh_sach_giay_nop_tien.json"), ("notice", make_tb_handler, "danh_sach_thong_bao.json")]:
            with self.subTest(mode=mode):
                config = self.config(mode)
                config.validate()
                cancel = Event()
                hooks = RunHooks(cancel, lambda payload, token=cancel: token.set() if "record" in payload else None)
                result = run_online(config, hooks, StubCaptcha(), logging.getLogger("gdt_tax.test"), http=FakeHttp(factory({})))
                self.assertEqual(result.state, "CANCELLED")
                self.assertEqual(result.downloaded, 1)
                rows = json.loads((config.output / metadata).read_text(encoding="utf-8"))
                self.assertEqual(len(rows), 1)
                self.assertTrue(any(p.suffix in {".zip", ".xml", ".pdf"} for p in config.output.iterdir()))

    def test_failure_after_first_record_retains_committed_metadata(self):
        from gdt_tax.errors import NetworkError
        config = self.config()
        config.validate()
        delegate = make_legacy_handler({})
        downloads = 0

        def handler(method, path, kwargs):
            nonlocal downloads
            if "downTkhai" in str(kwargs):
                downloads += 1
                if downloads == 2:
                    raise NetworkError("fixture connection failure")
            return delegate(method, path, kwargs)

        result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger("gdt_tax.test"), http=FakeHttp(handler))
        self.assertEqual(result.state, "ERROR")
        self.assertEqual(result.downloaded, 1)
        self.assertEqual(len(result.rows), 2)
        self.assertTrue((config.output / "danh_sach_ho_so.json").is_file())

    def test_offline_matches_all_four_cli_stages_without_network(self):
        source = self.root / "Nguồn tiếng Việt"
        source.mkdir()
        for file in FIXTURES.glob("*.xml"):
            shutil.copyfile(file, source / file.name)
        config = self.config("offline", source=source)
        config.validate()
        with patch("socket.socket.connect", side_effect=AssertionError("offline network")):
            result = run_offline(config, RunHooks(), logging.getLogger("gdt_tax.test"))
            self.assertTrue(result.rows)
            cli_output = self.root / "cli"
            self.assertEqual(inventory.main([str(source), "--output", str(cli_output)]), 0)
            # This fixture set contains unmapped/unknown forms: files are written,
            # while CLI and desktop both report partial quality.
            self.assertEqual(result.state, "PARTIAL")
            self.assertEqual(parse_cli([str(source), "--manifest", str(cli_output / inventory.MANIFEST_NAME), "--output", str(cli_output)]), 1)
            self.assertEqual(classify.main([str(source), "--manifest", str(cli_output / inventory.MANIFEST_NAME), "--output", str(cli_output)]), 1)
            self.assertEqual(export.main([str(cli_output)]), 1)
        for name in ["parsed_declarations.json", "phan_loai_artifact.json"]:
            self.assertEqual(json.loads((config.output / name).read_text(encoding="utf-8")), json.loads((cli_output / name).read_text(encoding="utf-8")))
        from openpyxl import load_workbook
        first = load_workbook(config.output / export.WORKBOOK_NAME, read_only=True)
        second = load_workbook(cli_output / export.WORKBOOK_NAME, read_only=True)
        for sheet in ["01_RETURN_INDEX", "05_INDICATORS", "07_UNMAPPED_FORMS"]:
            self.assertEqual(list(first[sheet].values), list(second[sheet].values))
        first.close()
        second.close()

    def test_missing_offline_dependency_reports_stage_error(self):
        config = self.config("offline", source=FIXTURES, stage="export")
        config.validate()
        result = run_offline(config, RunHooks(), logging.getLogger("gdt_tax.test"))
        self.assertEqual(result.state, "ERROR")
        self.assertIn("export", result.message)
        self.assertEqual(result.files, [])

    def test_settings_whitelist_and_future_schema_protection(self):
        store = SettingsStore(self.root / "settings.json")
        store.save(self.prefs)
        raw = json.loads(store.path.read_text())
        self.assertFalse({"password", "username", "proxy", "dvc"} & raw.keys())
        raw.update(password="must-not-load", username="must-not-load", schema_version=99)
        store.path.write_text(json.dumps(raw))
        with self.assertRaises(ValueError):
            store.load()
        with self.assertRaises(ValueError):
            store.save(self.prefs)
        self.assertEqual(json.loads(store.path.read_text())["schema_version"], 99)

    def test_hooks_cancel_pause_and_offline_at_boundary(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(RunCancelled):
            RunHooks(cancel).pause(100)
        with self.assertRaises(RunCancelled):
            inventory.scan_directory(FIXTURES, hooks=RunHooks(cancel))

    def test_http_retry_stops_without_second_request(self):
        from gdt_tax.http import HttpClient
        from tests.support import FakeResponse
        cancel = Event()

        class Session:
            headers = {}
            calls = 0

            def request(self, *_args, **_kwargs):
                self.calls += 1
                cancel.set()
                return FakeResponse(status_code=429, headers={"Retry-After": "300"})

            def close(self):
                pass

        session = Session()
        client = HttpClient(session=session, hooks=RunHooks(cancel))
        with self.assertRaises(RunCancelled):
            client.get("/fixture")
        self.assertEqual(session.calls, 1)

    def test_cancelled_unattempted_record_is_not_counted_as_download_error(self):
        config = self.config()
        config.validate()
        cancel = Event()
        delegate = make_legacy_handler({})

        def handler(method, path, kwargs):
            if "downTkhai" in str(kwargs):
                cancel.set()
                raise RunCancelled()
            return delegate(method, path, kwargs)

        result = run_online(config, RunHooks(cancel), StubCaptcha(), logging.getLogger("gdt_tax.test"), http=FakeHttp(handler))
        self.assertEqual(result.state, "CANCELLED")
        self.assertEqual(result.errors, 0)
        self.assertEqual(result.discovered, 1)


@unittest.skipUnless(HAS_QT, "Install requirements-desktop.txt for Qt tests")
class QtDesktopTests(unittest.TestCase):
    setUp = DesktopTests.setUp
    tearDown = DesktopTests.tearDown
    config = DesktopTests.config
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_until(self, predicate, seconds=10):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def test_worker_prevents_double_start_and_resets_after_failure(self):
        controller = JobController()
        config = self.config("offline", source=FIXTURES, stage="export")
        results = []
        controller.completed.connect(results.append)
        self.assertTrue(controller.start(config))
        self.assertFalse(controller.start(config))
        self.wait_until(lambda: bool(results))
        self.assertFalse(controller.busy)
        self.assertEqual(results[0].state, "ERROR")

    def test_gui_captcha_answer_and_cancel_never_call_input(self):
        for answer in ["abc12", None]:
            requests, values = [], []
            cancel = Event()
            solver = GuiCaptchaSolver(RunHooks(cancel), requests.append, use_ocr=False)

            def solve(solver=solver, values=values):
                try:
                    values.append(solver.solve(b"image"))
                except RunCancelled:
                    values.append("cancelled")

            thread = Thread(target=solve)
            with patch("builtins.input", side_effect=AssertionError("console input called")):
                thread.start()
                self.wait_until(lambda pending=requests: bool(pending))
                requests[0].respond(answer)
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(values, [answer if answer else "cancelled"])

    def test_redaction_masks_proxy_headers_password_and_url_tokens(self):
        config = self.config(proxy="http://proxy-user:proxy-password@127.0.0.1:8888", extra_headers={"Authorization": "Bearer test-token"})
        redact = Redactor(config)
        text = redact(f"{config.password} {config.username} proxy-password Bearer test-token https://example.test/a?session=secret")
        for secret in [config.password, config.username, "proxy-password", "test-token", "session=secret"]:
            self.assertNotIn(secret, text)

    def test_captcha_dialog_is_visible_and_returns_answer(self):
        from PySide6.QtCore import QTimer
        window = MainWindow(SettingsStore(self.root / "settings.json"))
        request = CaptchaRequest((FIXTURES / "sample_captcha.png").read_bytes())

        def answer():
            dialog = window.captcha_dialog
            self.assertIsInstance(dialog, QDialog)
            dialog.findChild(QLineEdit).setText("abc12")
            dialog.accept()

        QTimer.singleShot(20, answer)
        window.on_captcha(request)
        self.assertEqual(request.answer, "abc12")
        window.close()

    def test_narrow_layout_all_actions_inside_window_and_settings_scroll_only(self):
        window = MainWindow(SettingsStore(self.root / "settings.json"))
        window.show()
        self.app.processEvents()
        window.resize(682, 450)
        self.app.processEvents()
        self.assertTrue(window.ultra)
        for index in range(4):
            window.tabs.setCurrentIndex(index)
            window.subview.setCurrentIndex(0)
            self.app.processEvents()
            # Hidden widgets keep their pre-layout geometry; check the navigation
            # control that is actually shown at this width (tabs or combo).
            navigation = window.tabs if window.tabs.isVisible() else window.navigation
            for widget in [window.output, window.start_button, window.stop_button, navigation]:
                self.assertTrue(window.rect().contains(widget.mapTo(window, widget.rect().bottomRight())))
        dialog = AdvancedDialog(window)
        self.assertTrue(dialog.findChildren(__import__("PySide6.QtWidgets", fromlist=["QScrollArea"]).QScrollArea))
        dialog.close()
        window.close()

    def test_switching_four_tabs_ten_times_does_not_touch_session_or_login(self):
        window = MainWindow(SettingsStore(self.root / "settings.json"))
        calls = []
        with patch.object(window.controller.sessions, "execute",
                          side_effect=lambda *args, **kwargs: calls.append((args, kwargs))):
            for _ in range(10):
                for index in range(4):
                    window.tabs.setCurrentIndex(index)
                    self.app.processEvents()
        self.assertEqual(calls, [])
        window.close()

    def test_close_running_job_requests_stop_and_waits_for_worker(self):
        from PySide6.QtWidgets import QMessageBox

        from desktop.services import JobResult
        window = MainWindow(SettingsStore(self.root / "settings.json"))

        def slow_offline(config, hooks, _logger):
            hooks.cancel.wait(5)
            return JobResult("CANCELLED", "Đã dừng", config.output)

        with patch("desktop.jobs.run_offline", side_effect=slow_offline), patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            config = self.config("offline", source=FIXTURES)
            window.show()
            window.controller.start(config)
            window.close()
            self.assertTrue(window.controller.cancel.is_set())
            self.wait_until(lambda: not window.controller.busy)
            self.assertFalse(window.isVisible())

    def test_fit_screen_keeps_frame_inside_small_and_negative_origin_workareas(self):
        from types import SimpleNamespace

        from PySide6.QtCore import QRect
        window = MainWindow(SettingsStore(self.root / "settings.json"))
        window.show()
        self.app.processEvents()
        for area in [QRect(0, 0, 682, 485), QRect(-819, 0, 819, 582)]:
            window.resize(1080, 670)
            window.move(1600, 900)
            with patch.object(window, "screen", return_value=SimpleNamespace(availableGeometry=lambda area=area: area)):
                window.fit_screen()
            self.app.processEvents()
            self.assertTrue(area.contains(window.frameGeometry()), str(window.frameGeometry()))
        window.close()
