"""Typed interfaces and scoped artifacts work without requests response objects."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

from gdt_tax.contracts import (
    DownloadArtifact,
    QueryOutcome,
    Solver,
    Store,
    Transport,
    checked_artifact,
)
from gdt_tax.errors import DownloadError
from gdt_tax.gnt.models import GiayNopTien, GntPageResult
from gdt_tax.gnt.storage import GntStore
from gdt_tax.http import HttpClient
from gdt_tax.models import CaseRecord, PageResult
from gdt_tax.storage import ZipStore
from gdt_tax.tb.models import TbPageResult, ThongBao
from gdt_tax.tb.storage import TbStore
from tests.support import FakeHttp, FakeResponse, StubCaptcha, sample_zip

if TYPE_CHECKING:
    # CI type checking verifies concrete structural compatibility as well.
    def transport_contract(client: HttpClient, solver: Solver) -> tuple[Transport, Solver]:
        return client, solver

    def store_contracts(tax: ZipStore, gnt: GntStore, notice: TbStore) -> tuple[Store[CaseRecord], Store[GiayNopTien], Store[ThongBao]]:
        return tax, gnt, notice

    def query_contracts(tax: PageResult, gnt: GntPageResult, notice: TbPageResult) -> tuple[QueryOutcome[CaseRecord], QueryOutcome[GiayNopTien], QueryOutcome[ThongBao]]:
        return tax, gnt, notice


class CoreContractTests(unittest.TestCase):
    def test_fake_transport_needs_only_small_http_contract(self):
        http = FakeHttp(lambda *_: FakeResponse('synthetic'))
        self.assertIsInstance(http, Transport)
        self.assertIsInstance(StubCaptcha(), Solver)
        self.assertEqual(http.get('/page').text, 'synthetic')

    def test_scoped_artifact_cannot_be_saved_as_another_record(self):
        record = CaseRecord('synthetic', 'ETAX_LEGACY', account_key='account')
        artifact = DownloadArtifact(sample_zip(), 'zip', 'DECLARATION', record.key)
        self.assertEqual(checked_artifact(artifact, record), artifact.data)
        self.assertEqual(len(artifact.sha256), 64)
        for other in (CaseRecord('synthetic', 'DVC', account_key='account'),
                      CaseRecord('synthetic', 'ETAX_LEGACY', account_key='other')):
            with self.assertRaisesRegex(DownloadError, 'SCOPE_MISMATCH'):
                checked_artifact(artifact, other)
        self.assertFalse(hasattr(artifact, 'json'))
        self.assertFalse(hasattr(artifact, 'status_code'))
        with tempfile.TemporaryDirectory() as directory:
            path = ZipStore(Path(directory)).save(record, checked_artifact(artifact, record))
            self.assertTrue(path.is_file())

