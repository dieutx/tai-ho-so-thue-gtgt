"""Synthetic secrets only; support evidence must omit payloads by default."""
from __future__ import annotations

import io
import json
import logging
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from gdt_tax.logging_setup import SecretsFilter
from gdt_tax.redaction import exception_summary, redact_text, safe_url
from gdt_tax.traffic import TrafficDumper, body_as_text, mask_headers
from tests.support import temporary_directory
from tests.test_http import FakeSession, StubResponse
from tests.test_traffic import StubResponse as TrafficResponse


class RedactionContracts(unittest.TestCase):
    def test_json_strings_nested_arrays_form_and_html_are_structured(self):
        payloads = [json.dumps({"password": "fake-secret", "nested": [{"token": "fake-secret"}]}),
                    "password=fake%2Dsecret&csrf=fake%2Dsecret&page=1",
                    '<form><input name="_csrf" value="fake-secret"><textarea>fake-secret</textarea></form>',
                    json.dumps({"nested": json.dumps({"token": "fake-secret"})})]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertNotIn("fake-secret", body_as_text(payload))
                self.assertNotIn("fake%2Dsecret", body_as_text(payload))

    def test_url_referer_location_and_userinfo_do_not_keep_sessions(self):
        url = "https://user:fake-secret@thuedientu.gdt.gov.vn/etaxnnt/Request?dse_sessionId=fake-secret#fake-secret"
        self.assertNotIn("fake-secret", safe_url(url))
        headers = mask_headers({"Referer": url, "Location": url, "X-New-Token": "fake-secret"})
        self.assertNotIn("fake-secret", json.dumps(headers))
        self.assertNotIn("fake-secret", redact_text("redirected to " + url))

    def test_shared_dump_contains_no_original_payload_or_tax_data(self):
        with temporary_directory() as tmp:
            dumper = TrafficDumper(tmp)
            paths = dumper.record(method="POST", url="https://example.test/search?token=fake-secret",
                body={"unrecognized_taxpayer_field": "synthetic-sensitive-taxpayer"},
                response=TrafficResponse('<html>synthetic-sensitive-taxpayer<input value="fake-secret"></html>'),
                headers={"Referer": "https://example.test/search?session=fake-secret"})
            self.assertEqual(len(paths), 2)
            shared = "\n".join(path.read_text(encoding="utf-8") for path in paths)
            self.assertNotIn("fake-secret", shared)
            self.assertNotIn("synthetic-sensitive-taxpayer", shared)
            self.assertIn("sha256=", shared)
            self.assertEqual(list(Path(tmp).rglob("*.body")), [])

    def test_private_dump_is_separate_bounded_and_expires(self):
        with temporary_directory() as tmp:
            now = [datetime(2026, 1, 1)]
            dumper = TrafficDumper(tmp, private=True, max_body_bytes=3,
                                   max_records=1, clock=lambda: now[0])
            paths = dumper.record(method="GET", url="https://example.test/x",
                                  response=TrafficResponse(content=b"abcdef"))
            self.assertIn("PRIVATE", str(paths[2]))
            self.assertEqual(paths[2].read_bytes(), b"abc")
            self.assertEqual(dumper.record(method="GET", url="https://example.test/x", response=TrafficResponse()), [])
            expiring = TrafficDumper(tmp, private=True, clock=lambda: now[0])
            now[0] += timedelta(minutes=16)
            self.assertEqual(expiring.record(method="GET", url="https://example.test/x", response=TrafficResponse()), [])

    def test_http_info_and_debug_never_log_raw_login_or_tax_payload(self):
        from gdt_tax.http import HttpClient
        client = HttpClient(session=FakeSession([StubResponse(200, text="synthetic-sensitive-taxpayer")]))
        with self.assertLogs("gdt_tax.http", level="DEBUG") as captured:
            client.post("/loginLDAP?token=fake-secret", data={"new_field": "synthetic-sensitive-taxpayer"})
        text = "\n".join(captured.output)
        self.assertNotIn("fake-secret", text)
        self.assertNotIn("synthetic-sensitive-taxpayer", text)
        self.assertIn("loginLDAP", text)

    def test_exception_formatter_and_crash_summary_omit_messages_and_source_lines(self):
        try:
            raise ValueError("synthetic-sensitive-taxpayer https://example.test/x?token=fake-secret")
        except ValueError as error:
            import sys
            info = sys.exc_info()
            crash = exception_summary(type(error), error, error.__traceback__)
            record = logging.LogRecord("gdt_tax.test", logging.ERROR, __file__, 1,
                                       "failed token=fake-secret", (), info)
        SecretsFilter().filter(record)
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.emit(record)
        for text in (stream.getvalue(), crash):
            self.assertNotIn("fake-secret", text)
            self.assertNotIn("synthetic-sensitive-taxpayer", text)
        self.assertIn("ValueError", crash)

    def test_frozen_crash_hook_keeps_only_frames_and_rotates_private_file(self):
        import sys

        import desktop.crash_log as crash_log
        old_hook = sys.excepthook
        with temporary_directory() as tmp:
            target = Path(tmp) / "TaiHoSoThue" / "PRIVATE" / "crash.log"
            target.parent.mkdir(parents=True)
            target.write_text("x" * (1024 * 1024 + 1), encoding="utf-8")
            try:
                with patch.object(sys, "frozen", True, create=True), patch.dict(
                        "os.environ", {"LOCALAPPDATA": tmp}), patch("faulthandler.enable"):
                    crash_log.install_crash_log()
                try:
                    raise ValueError("fake-secret https://example.test/x?session=fake-secret")
                except ValueError:
                    sys.excepthook(*sys.exc_info())
                text = target.read_text(encoding="utf-8")
                self.assertNotIn("fake-secret", text)
                self.assertIn("ValueError", text)
                self.assertTrue(target.with_name("crash.previous.log").exists())
            finally:
                sys.excepthook = old_hook
                if crash_log._stream:
                    crash_log._stream.close()
                    crash_log._stream = None
