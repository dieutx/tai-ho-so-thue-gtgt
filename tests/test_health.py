"""Health evidence is safe/read-only and public probes never authenticate."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from gdt_tax.config import Settings
from gdt_tax.health import analyze_response, doctor, main, public_probe
from gdt_tax.http import HttpClient
from gdt_tax.models import PageResult
from gdt_tax.orchestration import search_page
from gdt_tax.parsing import parse_record_table
from gdt_tax.run_hooks import RunHooks
from tests.support import FakeResponse, fixture
from tests.test_http import FakeSession, StubResponse


class HealthTests(unittest.TestCase):
    def test_report_retains_quality_without_record_body_identifiers_or_tokens(self):
        html = fixture('dvc_results_page1.html') + '<input type="hidden" value="private-fixture-token">'
        report = analyze_response(FakeResponse(html), 'DVC', 'search')
        self.assertEqual(report['outcome'], 'PARSED')
        self.assertTrue(report['complete'])
        self.assertEqual(report['counts']['parsed'], 2)
        text = json.dumps(report)
        for secret in ('private-fixture-token', 'G12.18-', 'Thuế cơ sở', '<table', 'TỜ KHAI'):
            self.assertNotIn(secret, text)
        self.assertEqual(len(report['schema']['fingerprint']), 64)

    def test_health_unknown_empty_and_maintenance_stay_distinct(self):
        for html, outcome in (('<div id="totalPage">0</div>', 'SCHEMA_CHANGED'),
                              ('Hệ thống đang bảo trì', 'MAINTENANCE'),
                              ('<div id="table-container">Không có dữ liệu</div>', 'EMPTY_CONFIRMED')):
            self.assertEqual(analyze_response(FakeResponse(html), 'DVC', 'search')['outcome'], outcome)

    def test_public_probe_has_one_request_no_redirect_and_leaves_authentication_untested(self):
        session = FakeSession([StubResponse(302, {'Location': '/business/private'})])
        factory = Mock(side_effect=lambda **kwargs: HttpClient(session=session, **kwargs))
        report = public_probe('DVC', client_factory=factory)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0][0], 'GET')
        self.assertTrue(session.calls[0][1].endswith('/login'))
        self.assertFalse(session.sent[0]['allow_redirects'])
        self.assertEqual(report['authenticated_capability'], 'UNTESTED')
        self.assertFalse(report['complete'])
        self.assertTrue(session.closed)
        self.assertEqual(factory.call_args.kwargs['hooks'].budget.max_requests, 1)
        self.assertEqual(report['verification_scope'], 'public_get_only')

    def test_doctor_and_invalid_input_validation_do_not_connect_or_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'parsed_declarations.json'
            file.write_text('{"private-data":"fake-token"}')
            before = file.read_bytes()
            report = doctor(root)
            self.assertEqual(report['outcome'], 'OFFLINE_INPUT_INVALID')
            self.assertEqual(file.read_bytes(), before)
            self.assertIsNone(report['last_verified_at'])
            self.assertNotIn('fake-token', json.dumps(report))
            self.assertNotIn(directory, json.dumps(report))
            self.assertTrue(doctor()['mappings'])

    def test_search_support_events_share_run_id_and_contain_no_raw_records(self):
        events = []
        hooks = RunHooks(support=events.append)
        settings = Settings('synthetic', 'private-password', date(2026, 1, 1), date(2026, 1, 1), Path('synthetic'))
        context = SimpleNamespace(hooks=hooks, settings=settings, logger=Mock())
        parsed = parse_record_table(fixture('dvc_results_page1.html'), 'DVC')
        for page in (1, 2):
            search_page(context, lambda: PageResult(parsed.records, 2, 200, parsed.diagnostics), 'DVC', page)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]['run_id'], events[1]['run_id'])
        self.assertNotEqual(events[0]['operation_id'], events[1]['operation_id'])
        self.assertTrue(events[0]['schema_fingerprint'])
        self.assertNotIn('private-password', json.dumps(events))
        self.assertNotIn(parsed.records[0].ma_ho_so, json.dumps(events))

    def test_cli_is_offline_by_default_and_uses_partial_exit_for_unverified_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / 'doctor.json'
            self.assertEqual(main(['--output', str(report)]), 0)
            self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['live_verification'], 'NOT_PERFORMED')
            source = root / 'response.html'
            source.write_text('<div>synthetic unknown response</div>')
            self.assertEqual(main(['--fixture', str(source), '--output', str(report)]), 1)
            self.assertEqual(source.read_text(), '<div>synthetic unknown response</div>')
