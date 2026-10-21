"""One behavior matrix for tax/GNT/TB orchestration using minimal fake adapters."""
from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from gdt_tax.config import Settings
from gdt_tax.errors import SchemaChangedError, SearchError
from gdt_tax.gnt.models import GiayNopTien, GntPageResult
from gdt_tax.gnt.pipeline import GntPipeline
from gdt_tax.identity import account_fingerprint
from gdt_tax.models import CaseRecord, PageResult, SearchPeriod
from gdt_tax.pipeline import Pipeline
from gdt_tax.table_contracts import ParseDiagnostics
from gdt_tax.tb.models import TbPageResult, ThongBao
from gdt_tax.tb.pipeline import TbPipeline
from tests.support import StubCaptcha, temporary_directory

CASES = [(Pipeline, lambda key: CaseRecord(key, 'ETAX_LEGACY'), PageResult, 'search', 'ETAX_LEGACY'),
         (GntPipeline, GiayNopTien, GntPageResult, 'search_gnt', 'GNT'),
         (TbPipeline, ThongBao, TbPageResult, 'search_tb', 'TB')]


class PipelineContractTests(unittest.TestCase):
    def exercise(self, variant):
        for cls, make_record, outcome, method, source in CASES:
            with self.subTest(pipeline=cls.__name__), temporary_directory() as directory:
                settings = Settings(username='synthetic', password='fixture', from_date=date(2025, 1, 1),
                    to_date=date(2025, 1, 2), download_dir=Path(directory), search_attempts=2,
                    pause_between_records=0, pause_between_pages=0)
                pipeline = cls(settings, Mock(), StubCaptcha(), persist_metadata=False)
                trace = []
                def search(period, page, outcome=outcome, make_record=make_record, trace=trace):
                    trace.append(('search', page))
                    record = make_record('synthetic-1' if variant == 'repeated' else f'synthetic-{page}')
                    diagnostics = ParseDiagnostics(status='SCHEMA_CHANGED' if variant == 'partial' else 'PARSED',
                                                   reasons=['MISSING_FIELD'] if variant == 'partial' else [])
                    return outcome([record], 2, 200, diagnostics)
                portal = SimpleNamespace(source=source, **{method: search})
                def download(portal, record, succeeded, trace=trace):
                    trace.append(('download', record.key.remote_id))
                    succeeded.add(record.record_key)
                    return True
                pipeline._attempt_download = download
                operation = pipeline._search_and_download if cls is Pipeline else pipeline._search_period
                if variant == 'target':
                    record = make_record('synthetic-1')
                    record.account_key = account_fingerprint(settings.username)
                    pipeline.target_ids = {record.record_key}
                if variant in {'partial', 'repeated'}:
                    with self.assertRaises(SchemaChangedError if variant == 'partial' else SearchError):
                        operation(portal, SearchPeriod(settings.from_date, settings.to_date, source), pipeline.records, pipeline.downloaded_ids)
                else:
                    operation(portal, SearchPeriod(settings.from_date, settings.to_date, source), pipeline.records, pipeline.downloaded_ids)
                self.assertEqual(trace[:2], [('search', 1), ('download', 'synthetic-1')])
                if variant == 'normal':
                    self.assertEqual(trace[2:], [('search', 2), ('download', 'synthetic-2')])
                elif variant in {'target', 'partial'}:
                    self.assertEqual(len(trace), 2)
                else:
                    self.assertEqual(trace[2:], [('search', 2)])

    def test_search_then_immediate_download_before_next_page(self):
        self.exercise('normal')

    def test_partial_page_preserves_rows_and_fails_without_retry(self):
        self.exercise('partial')

    def test_repeated_page_cannot_claim_complete(self):
        self.exercise('repeated')

    def test_target_completion_stops_before_advancing_session(self):
        self.exercise('target')
