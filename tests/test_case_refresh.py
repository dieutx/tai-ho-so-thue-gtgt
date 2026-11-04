"""Targeted search and status refresh, with synthetic HTTP/HTML only."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from bs4 import BeautifulSoup

from gdt_tax.config import Settings
from gdt_tax.errors import SearchError
from gdt_tax.identity import account_fingerprint
from gdt_tax.models import CaseRecord, SearchPeriod
from gdt_tax.parsing import parse_records
from gdt_tax.pipeline import Pipeline
from gdt_tax.portals.canhan import CanhanPortal
from gdt_tax.portals.etax import EtaxPortal
from gdt_tax.portals.etax_legacy import EtaxLegacyPortal
from gdt_tax.processing_status import detail_processing_status
from tests.support import FakeHttp, FakeResponse, StubCaptcha, fixture
from tests.test_pipeline import make_handler


class CaseRefreshTests(unittest.TestCase):
    def test_personal_rental_form_with_notice_in_title_downloads_and_reuses(self):
        from desktop.documents import verify_rows
        from gdt_tax.classification import classify_record
        from gdt_tax.storage import ZipStore, required_document_kind
        from tests.support import sample_zip
        with tempfile.TemporaryDirectory() as folder:
            record = CaseRecord('synthetic-rental', 'DVC',
                                to_khai='01/BĐS - Thông báo doanh thu/Tờ khai thuế đối với hoạt động cho thuê bất động sản',
                                loai_tai_lieu='NOTICE')
            self.assertEqual(required_document_kind(record), 'declaration')
            self.assertEqual(classify_record(record).loai_tai_lieu, 'DECLARATION')
            store = ZipStore(folder)
            path = store.save(record, sample_zip())
            self.assertIsNotNone(path)
            self.assertEqual(store.find_existing(record), path)
            self.assertEqual(verify_rows('tax', [record.to_dict()], Path(folder))[0]['_file_status'], 'downloaded')

    def settings(self, folder, **kwargs):
        return Settings(username='synthetic-refresh', password='fixture',
                        from_date=date(2026, 1, 1), to_date=date(2026, 3, 31),
                        download_dir=Path(folder), login_attempts=1, search_attempts=1,
                        pause_between_records=0, pause_between_pages=0,
                        dvc_enabled=True, legacy_etax=False, **kwargs)

    def test_selected_dvc_queries_each_id_once_for_both_account_types(self):
        for account_type in ('DN', 'CN'):
            with self.subTest(account_type=account_type), tempfile.TemporaryDirectory() as folder:
                settings = self.settings(folder, account_type=account_type)
                records = parse_records(fixture('dvc_results_page1.html'), 'DVC')
                for record in records:
                    record.account_key = account_fingerprint(settings.username)
                queries = []

                def search(kwargs, queries=queries):
                    params = kwargs['params']
                    queries.append(dict(params))
                    soup = BeautifulSoup(fixture('dvc_results_page1.html'), 'lxml')
                    for tr in soup.select('tbody tr'):
                        if params['maHoSo'] not in tr.get_text():
                            tr.decompose()
                    soup.find(id='totalPage').string = '1'
                    soup.find(id='gotoPageInput')['max'] = '1'
                    return str(soup)

                http = FakeHttp(make_handler(search=search))
                pipeline = Pipeline(settings, http, StubCaptcha(), persist_metadata=False,
                                    download_notices=False, target_ids={r.record_key for r in records},
                                    input_rows=[r.to_dict() for r in records])
                summary = pipeline.run()
                self.assertTrue(summary.complete)
                self.assertEqual(len(queries), 2)
                self.assertEqual({q['maHoSo'] for q in queries}, {r.ma_ho_so for r in records})
                self.assertEqual({q['page'] for q in queries}, {1})
                self.assertEqual(set(pipeline.records), {r.record_key for r in records})

    def test_server_ignoring_filter_does_not_trigger_bulk_scan(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = self.settings(folder)
            record = CaseRecord('synthetic-absent', 'DVC', account_key=account_fingerprint(settings.username))
            count = []
            def search(kwargs):
                count.append(kwargs)
                return fixture('dvc_results_page1.html')
            pipeline = Pipeline(settings, FakeHttp(make_handler(search=search)), StubCaptcha(),
                                persist_metadata=False, target_ids={record.record_key})
            with self.assertRaisesRegex(SearchError, 'CASE_SEARCH_NOT_SCOPED'):
                pipeline.run()
            self.assertEqual(len(count), 1)
            self.assertEqual(pipeline.records, {})

    def test_existing_zip_still_refreshes_detail_without_downloading_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = self.settings(folder)
            record = parse_records(fixture('dvc_results_page1.html'), 'DVC')[0]
            record.account_key = account_fingerprint(settings.username)
            base_handler = make_handler(search=lambda _: fixture('dvc_results_page1.html'))
            details = []
            def handler(method, path, kwargs):
                if '/files/detail/' in path:
                    details.append(path)
                    return FakeResponse('<html><head><meta name="_csrf" content="fixture"></head><body>'
                                        '<label>Trạng thái CQT</label><span>Đã chấp nhận</span></body></html>')
                return base_handler(method, path, kwargs)
            http = FakeHttp(handler)
            store = Mock()
            store.find_existing.return_value = True
            pipeline = Pipeline(settings, http, StubCaptcha(), store=store, download_notices=False,
                                persist_metadata=False)
            from gdt_tax.portals.dvc import DvcPortal
            record.trang_thai = 'Đã tiếp nhận'
            self.assertTrue(pipeline._download(DvcPortal(http, StubCaptcha(), settings), record, set()))
            self.assertEqual(record.trang_thai, 'Đã chấp nhận')
            self.assertEqual(record.trang_thai_tra_cuu, 'Đã tiếp nhận')
            self.assertEqual(len(details), 1)
            store.save.assert_not_called()

    def test_legacy_and_personal_send_their_own_transaction_fields(self):
        from tests.test_etax_legacy import SEARCH_START_HTML
        from tests.test_personal_accounts import DECLARATION_HTML, personal_settings
        period = SearchPeriod(date(2026, 1, 1), date(2026, 1, 31), 'ETAX_LEGACY')
        with tempfile.TemporaryDirectory() as folder:
            for cls, html, field in ((EtaxLegacyPortal, SEARCH_START_HTML, 'ma_gd'),
                                     (CanhanPortal, DECLARATION_HTML, 'maGDich')):
                with self.subTest(portal=cls.__name__):
                    settings = personal_settings() if cls is CanhanPortal else self.settings(folder)
                    portal = cls(FakeHttp(lambda *_: None), StubCaptcha(), settings)
                    portal._search_page_html = html
                    portal._search_page_url = 'https://example.test/Request'
                    with patch.object(portal, 'login'), patch.object(portal, '_post_form',
                            return_value=FakeResponse('', status_code=503)) as post:
                        portal.search(period, 1, case_id='synthetic-id')
                    self.assertEqual(post.call_args.args[3][field], 'synthetic-id')

    def test_etax_uses_its_transaction_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            def handler(method, path, kwargs):
                calls.append(kwargs)
                return FakeResponse('', status_code=500)
            portal = EtaxPortal(FakeHttp(handler), StubCaptcha(), self.settings(folder))
            with patch.object(portal, 'captcha_text', return_value='fixture'):
                portal.search(SearchPeriod(date(2025, 1, 1), date(2025, 1, 31), 'ETAX'),
                              1, case_id='synthetic-id')
            self.assertEqual(calls[-1]['data']['maGiaoDichTthc_tdt'], 'synthetic-id')


class ProcessingStatusTests(unittest.TestCase):
    def test_observed_dvc_detail_structure_uses_latest_end_time(self):
        # Public markup observed live; dates and all record values are synthetic.
        def step(end, state):
            return ('<div class="timeline"><div class="timeline-step"><div class="timeline-content">'
                    f'<strong><span>08:00 01/01/2026 - {end} 01/01/2026</span></strong>'
                    f'<ul><li><div class="d-flex"><p>Trạng thái hồ sơ: </p>'
                    f'<p class="text-warning"> {state}</p></div></li></ul></div></div></div>')
        for states in ((step('08:00', 'Chờ chấp nhận'), step('08:15', 'Đã chấp nhận')),
                       (step('08:15', 'Đã chấp nhận'), step('08:00', 'Chờ chấp nhận'))):
            self.assertEqual(detail_processing_status(''.join(states)), 'Đã chấp nhận')

    def test_waiting_for_acceptance_is_not_accepted(self):
        from desktop.domain import business_status_from_text
        self.assertEqual(business_status_from_text('Chờ chấp nhận'), 'unknown')
        self.assertEqual(business_status_from_text('Chưa chấp nhận'), 'unknown')
        self.assertEqual(detail_processing_status('<p>Trạng thái hồ sơ:</p><p>Chờ chấp nhận</p>'),
                         'Chờ chấp nhận')

    def test_later_acceptance_without_xml_and_reverse_history_order(self):
        for events in ((('31/10/2026 10:13', 'Đã tiếp nhận'), ('31/10/2026 10:20', 'Đã chấp nhận')),
                       (('31/10/2026 10:20', 'Đã chấp nhận'), ('31/10/2026 10:13', 'Đã tiếp nhận'))):
            html = '<label>Trạng thái</label><span>Đã tiếp nhận</span>'
            html += ''.join(f'<div class="timeline-item"><h5>{state}</h5><time>{when}</time></div>'
                            for when, state in events)
            self.assertEqual(detail_processing_status(html), 'Đã chấp nhận')

    def test_notice_titles_hidden_and_unrelated_text_are_not_decisions(self):
        self.assertEqual(detail_processing_status('''
            <div hidden><label>Trạng thái</label><span>Không chấp nhận</span></div>
            <div class="timeline-item"><h5>Chấp nhận/Không chấp nhận</h5></div>
            <a>Thông báo chấp nhận hồ sơ</a><p>Đã chấp nhận</p>'''), '')

    def test_portal_status_wins_over_receipt_xml_in_all_presentations(self):
        from desktop.documents import verify_rows
        from desktop.domain import submission_from_row
        from desktop.feedback_service import feedback_summary
        from desktop.reconciliation import reconciliation_rows
        with tempfile.TemporaryDirectory() as folder:
            row = CaseRecord('synthetic-extension', 'DVC', trang_thai='Đã chấp nhận').to_dict()
            notices = [{'kind': 'tiep-nhan', 'state': 'received', 'name': 'receipt.xml'}]
            row['_notices'] = notices
            self.assertEqual(feedback_summary(row).status, 'accepted')
            self.assertEqual(submission_from_row(row).tax_processing_status, 'accepted')
            self.assertEqual(reconciliation_rows([row])[0]['cqt_status'], 'Đã chấp nhận')
            verified = verify_rows('tax', [row], Path(folder))[0]
            self.assertEqual(verified['_cqt_status'], 'accepted')
            self.assertEqual(verified['_cqt_status_label'], 'Đã chấp nhận')

    def test_raw_portal_result_preserved_instead_of_receipt_xml(self):
        from desktop.feedback_service import feedback_summary
        row = {'trang_thai': 'Đã trả kết quả', '_notices': [{'state': 'received'}]}
        self.assertEqual(feedback_summary(row).status, 'unknown')
        self.assertEqual(feedback_summary(row).status_label, 'Đã trả kết quả')


if __name__ == '__main__':
    unittest.main()
