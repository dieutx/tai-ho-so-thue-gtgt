"""All five adapters consume reviewed profile descriptors and capability limits."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gdt_tax.config import Settings
from gdt_tax.contracts import DownloadArtifact
from gdt_tax.errors import ConfigError, SchemaChangedError
from gdt_tax.gnt.models import GiayNopTien, GntPageResult
from gdt_tax.gnt.pipeline import GntPipeline
from gdt_tax.gnt.portal import GntPortal
from gdt_tax.models import SearchPeriod
from gdt_tax.pipeline import Pipeline
from gdt_tax.portal_profiles import ETAX_PROFILE, LEGACY_PROFILES, profile_for
from gdt_tax.portals.etax import EtaxPortal
from gdt_tax.portals.etax_legacy import EtaxLegacyPortal
from gdt_tax.table_contracts import ParseDiagnostics
from gdt_tax.tb.models import TbPageResult, ThongBao
from gdt_tax.tb.pipeline import TbPipeline
from gdt_tax.tb.portal import TbPortal
from tests.support import FakeHttp, FakeResponse, StubCaptcha, fixture, temporary_directory


def settings(root=Path('synthetic')):
    return Settings('synthetic', 'fixture', date(2025, 1, 1), date(2025, 1, 10), root,
                    dry_run=True, pause_between_records=0, pause_between_pages=0)


class ProfileCoverageTests(unittest.TestCase):
    def test_all_packaged_adapters_have_valid_versioned_capabilities(self):
        for source in ('DVC', 'ETAX', 'ETAX_LEGACY', 'GNT', 'TB'):
            profile = profile_for(settings(), source)
            profile.validate()
            self.assertTrue(profile.version)
            self.assertTrue(profile.document_kinds)
            self.assertGreater(profile.max_days, 0)

    def test_health_analysis_uses_the_same_packaged_profile_as_business_adapters(self):
        from gdt_tax.health import analyze_response
        original = LEGACY_PROFILES[0]
        profile = replace(original, version='synthetic-v4', operation='reviewedOperation', form_id='reviewedForm', table_id='reviewedTable')
        html = fixture('etax_legacy_results.html').replace(original.operation, profile.operation).replace(original.form_id, profile.form_id).replace(original.table_id, profile.table_id)
        with patch('gdt_tax.portal_profiles.LEGACY_PROFILES', (profile, *LEGACY_PROFILES[1:])):
            report = analyze_response(FakeResponse(html), 'ETAX_LEGACY', 'search')
        self.assertEqual(report['outcome'], 'PARSED')
        self.assertEqual(report['profile_version'], profile.version)
        self.assertEqual(report['counts']['parsed'], 2)

    def test_legacy_operation_form_endpoint_page_and_table_mutations_use_actual_adapters(self):
        cases = [(EtaxLegacyPortal, 'ETAX_LEGACY', 'etax_legacy_results.html', 'search'),
                 (GntPortal, 'GNT', 'gnt_results_page1.html', 'search_gnt'),
                 (TbPortal, 'TB', 'tb_results_page1.html', 'search_tb')]
        for cls, source, name, search in cases:
            with self.subTest(source=source):
                original = profile_for(settings(), source)
                profile = replace(original, version='synthetic-v2', operation='reviewedOperation', form_id='reviewedForm',
                    table_id='reviewedResults', endpoint='/etaxnnt/ReviewedRequest', page_parameter='pageNo', query_event='reviewedQuery')
                configured = replace(settings(), legacy_profiles=tuple(profile if p.source == source else p for p in LEGACY_PROFILES))
                html = fixture(name).replace(original.operation, profile.operation).replace(original.form_id, profile.form_id).replace(original.table_id, profile.table_id).replace('/etaxnnt/Request', profile.endpoint)
                http = FakeHttp(lambda *_args, html=html, profile=profile: FakeResponse(html, url=profile.request_url))
                portal = cls(http, StubCaptcha(), configured)
                portal.login = Mock()
                portal._search_page_html, portal._search_page_url, portal._search_form_id = html, profile.request_url, profile.form_id
                result = getattr(portal, search)(SearchPeriod(configured.from_date, configured.to_date, source), 2)
                self.assertTrue(result.diagnostics.complete, result.diagnostics.reasons)
                self.assertEqual(len(result.records), 2)
                call = http.calls[0]
                self.assertEqual(call.path, profile.endpoint)
                payload = call.kwargs.get('data') or call.kwargs.get('params')
                self.assertEqual(str(payload['pageNo']), '2')
                self.assertEqual(payload['dse_operationName'], profile.operation)
                self.assertEqual(payload['dse_nextEventName'], profile.query_event)

    def test_etax_endpoint_form_page_scope_and_pagination_are_profiled(self):
        profile = replace(ETAX_PROFILE, version='synthetic-etax-v2', search_endpoint='/reviewed/search',
            form_id='reviewedForm', page_parameter='pageNo', result_container='reviewedResults', page_total_id='reviewedPage', page_input_id='reviewedPage')
        configured = replace(settings(), etax_profile=profile, legacy_etax=False, dvc_enabled=True)
        html = fixture('etax_results.html').replace('bangKetQuaTraCuu_tdt', 'reviewedResults').replace('goToPage_tdt', 'reviewedPage')
        http = FakeHttp(lambda *_: FakeResponse(html))
        portal = EtaxPortal(http, StubCaptcha(), configured)
        portal.captcha_text = lambda: 'synthetic'
        result = portal.search(configured.periods()[0], 2)
        self.assertTrue(result.diagnostics.complete)
        self.assertEqual(len(result.records), 2)
        self.assertEqual(http.calls[0].path, '/reviewed/search')
        self.assertEqual(http.calls[0].kwargs['data']['pageNo'], 2)
        self.assertEqual(http.calls[0].kwargs['headers']['HX-Trigger'], 'reviewedForm')
        self.assertEqual(result.total_pages, 1)

    def test_routing_uses_etax_and_legacy_date_capabilities(self):
        profile = replace(profile_for(settings(), 'ETAX_LEGACY'), max_days=2)
        configured = replace(settings(), legacy_profiles=tuple(profile if p.source == profile.source else p for p in LEGACY_PROFILES))
        self.assertEqual([p.end.day for p in configured.periods()], [2, 4, 6, 8, 10])
        configured = replace(settings(), legacy_etax=False, dvc_enabled=True, etax_profile=replace(ETAX_PROFILE, max_days=3))
        self.assertEqual([p.end.day for p in configured.periods()], [3, 6, 9, 10])

    def test_gnt_tb_limits_and_output_lineage_follow_their_profiles(self):
        for cls, source, method, record_type, outcome_type in (
            (GntPipeline, 'GNT', 'search_gnt', GiayNopTien, GntPageResult),
            (TbPipeline, 'TB', 'search_tb', ThongBao, TbPageResult)):
            with self.subTest(source=source), temporary_directory() as directory:
                profile = replace(profile_for(settings(), source), version='synthetic-v3', max_days=3)
                configured = replace(settings(Path(directory)), legacy_profiles=tuple(profile if p.source == source else p for p in LEGACY_PROFILES))
                def query(period, page, record_type=record_type, outcome_type=outcome_type):
                    return outcome_type([record_type('synthetic-' + str(period.start.day))], 1, 200, ParseDiagnostics(status='PARSED'))
                search = Mock(side_effect=query)
                portal = SimpleNamespace(**{method: search})
                pipeline = cls(configured, FakeHttp(lambda *_: None), StubCaptcha(), portal_factory=lambda portal=portal: portal)
                summary = pipeline.run()
                self.assertEqual([call.args[0].end.day for call in search.call_args_list], [3, 6, 9, 10])
                self.assertEqual(summary.portal_profile_version, profile.version)
                self.assertTrue(all(r.portal_profile_version == profile.version and r.routing_version == 'direct-source-v1' for r in pipeline.records.values()))
                self.assertFalse(list(Path(directory).iterdir()))

    def test_missing_duplicate_wrong_source_or_unsafe_profiles_fail_closed(self):
        for profiles in ((), LEGACY_PROFILES + (LEGACY_PROFILES[0],)):
            with self.assertRaises(ConfigError):
                profile_for(replace(settings(), legacy_profiles=profiles), 'ETAX_LEGACY')
        with self.assertRaises(ConfigError):
            profile_for(replace(settings(), etax_profile=replace(ETAX_PROFILE, source='DVC')), 'ETAX')
        for profile in (replace(LEGACY_PROFILES[0], operation='x;alert(1)'),
                        replace(LEGACY_PROFILES[0], endpoint='https://other.test/Request'),
                        replace(LEGACY_PROFILES[0], pagination='parallel')):
            with self.assertRaises(ConfigError):
                profile.validate()

    def test_unrecognized_legacy_queries_stop_after_one_request(self):
        for portal_type, pipeline_type, source, name in (
            (EtaxLegacyPortal, Pipeline, 'ETAX_LEGACY', 'etax_legacy_results.html'),
            (GntPortal, GntPipeline, 'GNT', 'gnt_results_page1.html'),
            (TbPortal, TbPipeline, 'TB', 'tb_results_page1.html')):
            with self.subTest(source=source):
                configured = replace(settings(), search_attempts=6)
                http = FakeHttp(lambda *_: FakeResponse('<html>synthetic unknown operation page</html>'))
                portal = portal_type(http, StubCaptcha(), configured)
                portal.login = Mock()
                profile = profile_for(configured, source)
                portal._search_page_html, portal._search_page_url, portal._search_form_id = fixture(name), profile.request_url, profile.form_id
                pipeline = pipeline_type(configured, http, StubCaptcha(), persist_metadata=False, sleep=lambda _: None)
                with self.assertRaises(SchemaChangedError):
                    pipeline._search_page(portal, SearchPeriod(configured.from_date, configured.to_date, source), 1)
                self.assertEqual(len(http.calls), 1)

    def test_profiled_downloads_keep_original_remote_ids_and_document_kinds(self):
        from tests.test_etax_legacy import XML_BODY
        from tests.test_gnt import GNT_XML
        from tests.test_tb import TB_PDF
        cases = [(EtaxLegacyPortal, 'ETAX_LEGACY', 'etax_legacy_results.html', 'search', 'download', XML_BODY, 'messageId'),
                 (GntPortal, 'GNT', 'gnt_results_page1.html', 'search_gnt', 'download_gnt', GNT_XML, 'ctuId'),
                 (TbPortal, 'TB', 'tb_results_page1.html', 'search_tb', 'download_tb', TB_PDF, 'messageId')]
        for cls, source, name, search, download, data, remote_field in cases:
            with self.subTest(source=source):
                original = profile_for(settings(), source)
                profile = replace(original, operation='reviewedOperation', form_id='reviewedForm',
                                  endpoint='/etaxnnt/ReviewedRequest', download_event='reviewedDownload')
                configured = replace(settings(), legacy_profiles=tuple(profile if p.source == source else p for p in LEGACY_PROFILES))
                html = fixture(name).replace(original.operation, profile.operation).replace(original.form_id, profile.form_id).replace('/etaxnnt/Request', profile.endpoint)
                def handler(method, path, kwargs, html=html, data=data, profile=profile):
                    payload = kwargs.get('data') or kwargs.get('params') or {}
                    return (FakeResponse(content=data) if payload.get('dse_nextEventName') == profile.download_event
                            else FakeResponse(html, url=profile.request_url))
                http = FakeHttp(handler)
                portal = cls(http, StubCaptcha(), configured)
                portal.login = Mock()
                portal._search_page_html, portal._search_page_url, portal._search_form_id = html, profile.request_url, profile.form_id
                record = getattr(portal, search)(SearchPeriod(configured.from_date, configured.to_date, source), 1).records[0]
                record.account_key = 'synthetic-account'
                result = portal.download(record, '', '') if source == 'ETAX_LEGACY' else getattr(portal, download)(record)
                self.assertIsNotNone(result)
                if isinstance(result, DownloadArtifact):
                    self.assertEqual(result.source, record.key)
                    self.assertEqual(result.document_kind, 'DECLARATION')
                else:
                    self.assertEqual(result, data)
                call = http.calls[-1]
                payload = call.kwargs.get('data') or call.kwargs.get('params')
                self.assertEqual(call.path, profile.endpoint)
                self.assertEqual(payload[remote_field], record.key.remote_id)
                self.assertEqual(payload['dse_operationName'], profile.operation)
                self.assertEqual(payload['dse_nextEventName'], profile.download_event)
