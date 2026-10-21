"""Profile mutations and routing coverage use real adapters without portal calls."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from gdt_tax.config import Settings
from gdt_tax.errors import ConfigError
from gdt_tax.pipeline import Pipeline
from gdt_tax.portal_profiles import DVC_PROFILE, RouteWindow, RoutingPolicy
from gdt_tax.portals.dvc import DvcPortal
from tests.support import FakeHttp, FakeResponse, StubCaptcha, fixture, temporary_directory
from tests.test_pipeline import make_handler


class PortalProfileTests(unittest.TestCase):
    def settings(self, root=Path('synthetic')):
        return Settings(username='synthetic', password='fixture', from_date=date(2025, 6, 30),
                        to_date=date(2025, 7, 1), download_dir=root, dvc_enabled=True,
                        pause_between_records=0, pause_between_pages=0, dry_run=True)

    def test_compatibility_boundaries_disabled_sources_and_max_range(self):
        settings = self.settings()
        self.assertEqual([(p.source, p.start, p.end) for p in settings.periods()], [
            ('ETAX_LEGACY', date(2025, 6, 30), date(2025, 6, 30)), ('DVC', date(2025, 7, 1), date(2025, 7, 1))])
        self.assertEqual(replace(settings, legacy_etax=False).periods()[0].source, 'ETAX')
        disabled = replace(settings, dvc_enabled=False).execution_plan()
        self.assertEqual([i['code'] for i in disabled.issues], ['SOURCE_DISABLED'])
        settings = replace(settings, from_date=date(2026, 1, 1), to_date=date(2026, 1, 10),
                           dvc_profile=replace(DVC_PROFILE, max_days=3))
        self.assertEqual([p.end.day for p in settings.periods()], [3, 6, 9, 10])

    def test_gap_overlap_and_effective_date_are_explicit(self):
        settings = self.settings()
        for windows, expected in (((), 'ROUTING_GAP'),
            ((RouteWindow('DVC', date.min, date.max), RouteWindow('ETAX_LEGACY', date.min, date.max)), 'ROUTING_OVERLAP')):
            policy = RoutingPolicy('synthetic-policy-v2', date.min, windows)
            plan = replace(settings, routing_policy=policy).execution_plan()
            self.assertEqual(plan.issues[0]['code'], expected)
        with self.assertRaisesRegex(ConfigError, 'ROUTING_RANGE_INVALID'):
            replace(settings, routing_policy=RoutingPolicy('future', date(2027, 1, 1), ())).execution_plan()

    def test_profile_changes_endpoint_form_page_and_response_contract_without_pipeline_edit(self):
        profile = replace(DVC_PROFILE, version='synthetic-v2', search_endpoint='/new/search',
                          form_id='newForm', page_parameter='pageNo', result_container='newResults',
                          page_total_id='newPageCount', page_input_id='newInput')
        settings = replace(self.settings(), from_date=date(2026, 1, 1), to_date=date(2026, 1, 1), dvc_profile=profile)
        calls = []
        html = fixture('dvc_results_page1.html').replace('table-container', 'newResults').replace('totalPage', 'newPageCount')
        def handler(method, path, kwargs):
            if path == '/new/search':
                calls.append(kwargs)
                return FakeResponse(html)
            return FakeResponse()
        portal = DvcPortal(FakeHttp(handler), StubCaptcha(), settings)
        portal.captcha_text = lambda: 'fixture'
        result = portal.search(settings.periods()[0], 2)
        self.assertTrue(result.diagnostics.complete)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(calls[0]['params']['pageNo'], 2)
        self.assertEqual(calls[0]['headers']['HX-Trigger'], 'newForm')
        self.assertEqual(calls[0]['headers']['HX-Target'], 'newResults')
        self.assertEqual(result.total_pages, 2)

    def test_gap_does_not_authenticate_or_claim_complete(self):
        with temporary_directory() as directory:
            settings = replace(self.settings(Path(directory)), routing_policy=RoutingPolicy('gap', date.min, ()))
            http = FakeHttp(lambda *_: self.fail('Gap plan must not authenticate'))
            summary = Pipeline(settings, http, StubCaptcha()).run()
            self.assertFalse(summary.complete)
            self.assertEqual(summary.routing_issues[0]['code'], 'ROUTING_GAP')
            self.assertEqual(summary.routing_version, 'gap')

    def test_profile_rejects_remote_urls_selectors_and_executable_descriptors(self):
        for profile in (replace(DVC_PROFILE, search_endpoint='https://evil.test/x'),
                        replace(DVC_PROFILE, form_id='x; alert(1)'), replace(DVC_PROFILE, max_days=0)):
            with self.assertRaises(ConfigError):
                profile.validate()

    def test_execution_plan_is_logged_before_login_and_record_lineage_uses_versions(self):
        with temporary_directory() as directory:
            settings = replace(self.settings(Path(directory)), from_date=date(2026, 1, 1), to_date=date(2026, 1, 1))
            pipeline = Pipeline(settings, FakeHttp(make_handler(search=lambda _: fixture('dvc_results_page1.html').replace('>2<', '>1<'))), StubCaptcha())
            # A one-page trace is sufficient; default fixture page count is two.
            from unittest.mock import patch
            with patch('gdt_tax.portals.dvc.DvcPortal.search') as search:
                from gdt_tax.models import CaseRecord, PageResult
                search.return_value = PageResult([CaseRecord('synthetic-1', 'DVC')], 1, 200)
                with self.assertLogs('gdt_tax', 'INFO') as logs:
                    summary = pipeline.run()
            self.assertTrue(summary.search_complete)
            self.assertIn('EXECUTION_PLAN', logs.output[0])
            record = next(iter(pipeline.records.values()))
            self.assertEqual(record.portal_profile_version, DVC_PROFILE.version)
            self.assertEqual(record.routing_version, summary.routing_version)

