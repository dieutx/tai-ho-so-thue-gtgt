"""Offline DVC primary/attachment quality and selective retry contracts."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from desktop.services import RunConfig, run_online
from gdt_tax.auth_outcomes import AuthFailure, AuthOutcome
from gdt_tax.config import Settings
from gdt_tax.dvc_notices import NoticeFile, NoticeStore, parse_notice_list
from gdt_tax.errors import NetworkError, StorageError
from gdt_tax.pipeline import Pipeline
from gdt_tax.run_hooks import RunCancelled, RunHooks
from tests.support import FakeHttp, FakeResponse, StubCaptcha, cleanup_temporary_directory, route_of
from tests.test_pipeline import dvc_search, make_handler

XML = b'<TBao><MaTB>synthetic-notice</MaTB></TBao>'
MODAL = ('<input name="_csrf" type="hidden" value="synthetic">'
         '<div id="modalThongBao"><div class="row"><div class="fw-bold">Synthetic</div>'
         '<a data-id="synthetic-1" onclick="downloadThongBao(this)">download</a></div></div>')


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = Settings(username='synthetic', password='fixture', from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31), download_dir=self.root, login_attempts=1, search_attempts=1,
            dvc_enabled=True, pause_between_records=0, pause_between_pages=0)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def pipeline(self, failure=None, detail=MODAL):
        base = make_handler(search=dvc_search)
        def handler(method, path, kwargs):
            if '/files/detail/' in path:
                return FakeResponse(detail)
            if route_of(path) == '/tchs/downloadthongbao':
                if isinstance(failure, Exception):
                    raise failure
                return failure or FakeResponse(content=XML)
            return base(method, path, kwargs)
        return Pipeline(self.settings, FakeHttp(handler), StubCaptcha(), sleep=lambda _: None)

    def test_attachment_failure_preserves_primary_and_counters_then_retry_only_missing(self):
        pipeline = self.pipeline(FakeResponse(status_code=500))
        summary = pipeline.run()
        self.assertTrue(summary.primary_complete)
        self.assertFalse(summary.complete)
        self.assertEqual(summary.downloaded, 2)
        self.assertEqual(summary.attachments_failed, 2)
        retry = self.pipeline()
        summary = retry.run()
        self.assertTrue(summary.complete)
        self.assertEqual(len(retry.reused_ids), 2)
        self.assertEqual(summary.attachments_downloaded, 2)
        third = self.pipeline()
        summary = third.run()
        self.assertEqual(summary.attachments_reused, 2)
        self.assertFalse(any(route_of(c.path) == '/tchs/downloadthongbao' for c in third.http.calls))
        for row in json.loads((self.root / 'danh_sach_ho_so.json').read_text(encoding='utf-8')):
            audit = json.loads(row['attachment_result'])
            self.assertTrue(audit['items'][0]['sha256'])
            self.assertTrue(audit['items'][0]['key'].startswith('ak1.'))
            attachment_path = Path(audit['items'][0]['path'])
            self.assertFalse(attachment_path.is_absolute())
            self.assertTrue((self.root / attachment_path).is_file())

    def test_auth_network_and_save_failure_are_independent_from_zip(self):
        for failure in (NetworkError('fixture'), AuthFailure(AuthOutcome.EXPIRED_SESSION),
                        AuthFailure(AuthOutcome.MAINTENANCE)):
            with self.subTest(failure=type(failure).__name__):
                summary = self.pipeline(failure).run()
                self.assertTrue(summary.primary_complete)
                self.assertFalse(summary.attachments_complete)
        with patch.object(NoticeStore, 'save', side_effect=StorageError('fixture')):
            summary = self.pipeline().run()
        self.assertTrue(summary.primary_complete)
        self.assertEqual(summary.attachments_failed, 2)

    def test_missing_csrf_and_schema_have_discovery_failure(self):
        for html in ('<div id="modalThongBao" data-empty="true"></div>',
                     '<input name="_csrf" value="fixture"><div>Unrecognized modal</div>'):
            pipeline = self.pipeline(detail=html)
            # Existing primary files still require explicit attachment discovery.
            with patch.object(pipeline.store, 'find_existing', return_value=Path('primary.zip')):
                summary = pipeline.run()
            self.assertTrue(summary.primary_complete)
            self.assertEqual(summary.attachments_failed, 2)

    def test_empty_modal_requires_evidence_and_never_reads_outside_scope(self):
        for html in ('', '<a data-id="outside" onclick="downloadThongBao(this)"></a>',
                     '<div id="modalThongBao"></div>', MODAL + MODAL,
                     MODAL.replace('downloadThongBao', 'newHandler')):
            self.assertEqual(parse_notice_list(html).status, 'SCHEMA_UNKNOWN')
        self.assertEqual(parse_notice_list('<div id="modalThongBao">Không có thông báo</div>').status, 'EMPTY_CONFIRMED')
        both = MODAL.replace('</div></div>', '<a data-id="synthetic-1" data-is-thue-dien-tu="true" onclick="downloadThongBao(this)"></a></div></div>')
        self.assertEqual(len(parse_notice_list(both).notices), 2)

    def test_cancel_during_attachment_preserves_primary_and_records_cancelled_quality(self):
        pipeline = self.pipeline(RunCancelled())
        with self.assertRaises(RunCancelled):
            pipeline.run()
        self.assertEqual(len(pipeline.downloaded_ids), 1)
        self.assertEqual(next(iter(pipeline.records.values())).attachment_status, 'CANCELLED')
        self.assertEqual(len(list(self.root.glob('*.zip'))), 1)

    def test_desktop_result_keeps_attachment_failures_separate(self):
        pipeline = self.pipeline(FakeResponse(status_code=500))
        config = RunConfig('tax', self.root, username='synthetic', password='fixture',
                           from_date='01/01/2026', to_date='31/01/2026', dvc=True)
        with patch('desktop.services.Pipeline', return_value=pipeline):
            result = run_online(config, RunHooks(), StubCaptcha(), Mock(), http=pipeline.http)
        self.assertEqual(result.state, 'PARTIAL')
        self.assertEqual(result.downloaded, 2)
        self.assertEqual(len(result.attachment_results), 2)

    def test_route_identity_and_title_changes_reuse_the_same_evidence(self):
        from gdt_tax.identity import RecordKey
        parent = RecordKey('account', 'DVC', 'DECLARATION', 'synthetic-case')
        notice = parse_notice_list(MODAL).notices[0]
        store = NoticeStore(self.root)
        path = store.save(parent, notice, NoticeFile('notice.xml', XML))
        notice.title = 'new display title'
        self.assertEqual(store.find_existing(parent, notice), path)
        self.assertIsNone(store.find_existing(parent, replace(notice, is_tdt=True)))

