"""Lookup completion regressions; synthetic records and temporary catalogs only."""
from __future__ import annotations

import importlib.util
import os
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from desktop.library import catalog_view
from desktop.services import JobResult
from desktop.settings_store import SettingsStore
from desktop.state import job_output
from gdt_tax.identity import account_fingerprint
from gdt_tax.local_catalog import LocalCatalog
from gdt_tax.models import CaseRecord, SearchPeriod
from gdt_tax.run_hooks import RunHooks
from tests.support import cleanup_temporary_directory
from tests.test_pipeline_contracts import CASES

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
USERNAME = 'synthetic-lookup-owner'
ACCOUNT = account_fingerprint(USERNAME)


class CatalogReadErrorTests(unittest.TestCase):
    def test_corrupt_database_is_reported_without_changing_bytes(self):
        import tempfile
        temporary = tempfile.TemporaryDirectory()
        try:
            base = Path(temporary.name)
            folder = job_output(base, USERNAME, 'tax')
            catalog = LocalCatalog(folder, ACCOUNT)
            catalog.path.write_bytes(b'synthetic invalid sqlite')
            before = catalog.path.read_bytes()
            result = catalog_view(base, USERNAME, 'tax', '01/10/2026', '31/10/2026')
            self.assertEqual(result.state, 'ERROR')
            self.assertIn('database', result.message)
            self.assertEqual(catalog.path.read_bytes(), before)
        finally:
            cleanup_temporary_directory(temporary)


class LookupPaginationTests(unittest.TestCase):
    def test_service_query_persists_all_pages_and_requeries_selected_months(self):
        import logging

        from desktop.services import RunConfig, run_online
        from desktop.settings_store import Preferences
        from gdt_tax.gnt.models import GiayNopTien, GntPageResult
        from tests.support import FakeHttp, StubCaptcha, temporary_directory

        with temporary_directory() as directory:
            base = Path(directory)
            folder = job_output(base, USERNAME, 'gnt')
            calls, progress = [], []

            class Portal:
                def search_gnt(self, period, page):
                    calls.append((period.start, period.end, page))
                    indices = range((page - 1) * 64, min(page * 64, 129))
                    return GntPageResult([GiayNopTien(f'{period.start.month}-{i}',
                                         ngay_lap=f'05/{period.start.month:02}/2025') for i in indices], 3, 200)

                def download_gnt(self, _record):
                    raise AssertionError('Query must not download')

            config = RunConfig('gnt', folder, username=USERNAME, password='synthetic', dry_run=True,
                               from_date='01/01/2025', to_date='28/02/2025',
                               preferences=Preferences(record_delay=0, page_delay=0, jitter=0))
            with patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP forbidden')):
                result = run_online(config, RunHooks(progress=progress.append), StubCaptcha(),
                                    logging.getLogger('test.lookup'), http=FakeHttp(lambda *_: None),
                                    portal_factory=Portal)
                self.assertEqual((result.state, result.discovered, result.downloaded), ('SUCCESS', 258, 0))
                self.assertEqual(progress[-1], {'stage': 'finalize'})
                self.assertEqual(calls, [(date(2025, month, 1), date(2025, month, last), page)
                                        for month, last in ((1, 31), (2, 28)) for page in (1, 2, 3)])
                for month in (1, 2):
                    view = catalog_view(base, USERNAME, 'gnt', f'01/{month:02}/2025', f'28/{month:02}/2025')
                    self.assertEqual(len(view.rows), 129)
                    self.assertTrue(all(r['ngay_lap'] == f'05/{month:02}/2025' for r in view.rows))
                repeated = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('test.lookup'),
                                      http=FakeHttp(lambda *_: None), portal_factory=Portal)
            self.assertEqual(repeated.sync_metrics['new'], 0)
            catalog = LocalCatalog(folder, ACCOUNT)
            self.assertEqual(catalog.get_counts('gnt')['total'], 258)
            self.assertEqual(catalog.integrity_check(), 'ok')

    def test_more_than_128_records_multiple_periods_and_repeated_pages(self):
        from gdt_tax.config import Settings
        from gdt_tax.errors import SearchError
        from tests.support import StubCaptcha, temporary_directory
        for cls, make_record, outcome, method, source in CASES:
            for repeated in (False, True):
                with self.subTest(mode=source, repeated=repeated), temporary_directory() as directory:
                    settings = Settings(username=USERNAME, password='synthetic', from_date=date(2025, 1, 1),
                                        to_date=date(2025, 1, 28), download_dir=Path(directory),
                                        pause_between_records=0, pause_between_pages=0)
                    progress, calls = [], []
                    pipeline = cls(settings, Mock(), StubCaptcha(), persist_metadata=False,
                                   hooks=RunHooks(progress=progress.append))

                    def search(period, page, outcome=outcome, make_record=make_record,
                               repeated=repeated, calls=calls):
                        calls.append((period.start, page))
                        if page <= 2:
                            first = (page - 1) * 64
                            keys = range(first, first + 64)
                        elif repeated:
                            keys = range(64)
                        else:
                            keys = [128]
                        return outcome([make_record(f'{period.start.month}-{key}') for key in keys], 3, 200)

                    portal = SimpleNamespace(source=source, **{method: search})

                    def download(_portal, record, succeeded):
                        succeeded.add(record.record_key)
                        return True

                    pipeline._attempt_download = download
                    operation = pipeline._search_and_download if source == 'ETAX_LEGACY' else pipeline._search_period
                    if repeated:
                        with self.assertRaises(SearchError):
                            operation(portal, SearchPeriod(settings.from_date, settings.to_date, source),
                                      pipeline.records, pipeline.downloaded_ids)
                        self.assertEqual(len(pipeline.records), 128)
                        continue
                    for month in (1, 2):
                        operation(portal, SearchPeriod(date(2025, month, 1), date(2025, month, 28), source),
                                  pipeline.records, pipeline.downloaded_ids)
                    self.assertEqual(len(pipeline.records), 258)
                    self.assertEqual(len(pipeline.downloaded_ids), 258)
                    self.assertEqual([page for _, page in calls], [1, 2, 3, 1, 2, 3])
                    self.assertEqual(progress[127]['discovered'], 128)
                    self.assertEqual(progress[128]['discovered'], 129)


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Optional desktop Qt dependencies')
class LookupCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import tempfile

        from desktop.ui import MainWindow
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.window = MainWindow(SettingsStore(self.root / 'settings.json'))
        self.window.output.setText(str(self.root))
        self.window.controller.sessions.set_account(USERNAME, 'synthetic-password')
        self.folder = job_output(self.root, USERNAME, 'tax')
        self.catalog = LocalCatalog(self.folder, ACCOUNT)
        self.catalog.upsert_documents('tax', [self.row('october', '05/10/2026'),
                                              self.row('september', '05/09/2026')])
        self.period(10)

    def tearDown(self):
        self.window.close()
        cleanup_temporary_directory(self.temporary)

    @staticmethod
    def row(key, day):
        return CaseRecord(key, 'DVC', account_key=ACCOUNT, ngay_nop=day,
                          ky_tinh_thue='Quý 3/2026', to_khai='01/GTGT').to_dict()

    def period(self, month):
        from PySide6.QtCore import QDate
        self.window.applying_preset = True
        self.window.from_date.setDate(QDate(2026, month, 1))
        self.window.to_date.setDate(QDate(2026, month, 28))
        self.window.applying_preset = False
        self.window.dates_changed()

    def complete(self, state='SUCCESS', **kwargs):
        self.window.active_config = self.window.make_config('tax', True)
        result = JobResult(state, 'Synthetic lookup result', self.folder,
                           account_key=ACCOUNT, date_range=('01/10/2026', '28/10/2026'),
                           operation='query', **kwargs)
        self.window.on_completed(result)
        return result

    def test_completion_keeps_query_outcome_and_selected_period(self):
        with patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP forbidden')):
            self.complete(discovered=1)
        self.assertEqual(self.window.result.state, 'SUCCESS')
        self.assertEqual(self.window.result.operation, 'query')
        self.assertEqual(self.window.result.date_range, ('01/10/2026', '28/10/2026'))
        self.assertEqual([r['ma_ho_so'] for r in self.window.model.rows], ['october'])
        self.assertEqual(self.window.model.rows[0]['ky_tinh_thue'], 'Quý 3/2026')
        self.assertIn('01/10/2026', self.window.status.text())
        self.assertEqual((self.window.progress.maximum(), self.window.progress.value()), (1, 1))

    def personal_catalog(self):
        self.window.controller.sessions.set_account_type('CN')
        self.window.controller.sessions.set_account(USERNAME, 'synthetic-password')
        folder = job_output(self.root, USERNAME, 'tax', 'CN')
        catalog = LocalCatalog(folder, ACCOUNT)
        catalog.upsert_documents('tax', [self.row(f'personal-{i}', '05/10/2026') for i in range(24)])
        return folder

    def test_personal_completion_reads_all_24_saved_rows_without_network(self):
        folder = self.personal_catalog()
        self.window.active_config = self.window.make_config('tax', False)
        with patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP forbidden')):
            self.window.on_completed(JobResult('PARTIAL', 'Seven files failed', folder,
                account_key=ACCOUNT, date_range=('01/10/2026', '28/10/2026'),
                operation='query_and_download', discovered=24, downloaded=17, errors=7))
        self.assertEqual(len(self.window.model.rows), 24)
        self.assertTrue(all(row['ma_ho_so'].startswith('personal-') for row in self.window.model.rows))
        self.assertEqual(self.window.result.output, folder)
        self.assertIn('Kho: 24', self.window.counts.text())
        self.assertIn('Online: 24', self.window.status.text())

    def test_personal_catalog_refresh_stays_in_personal_namespace(self):
        self.personal_catalog()
        with patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP forbidden')):
            self.window.apply_local_date_filter()
            self.assertEqual(len(self.window.model.rows), 24)
            self.period(9)
            self.assertEqual(self.window.model.rows, [])
            self.period(10)
            self.assertEqual(len(self.window.model.rows), 24)

    def test_personal_login_library_config_keeps_account_type(self):
        self.personal_catalog()
        with patch.object(self.window, 'launch') as launch:
            self.assertTrue(self.window.load_local_library())
        self.assertEqual(launch.call_args.args[0].account_type, 'CN')

    def test_failed_query_keeps_local_rows_and_clickable_error(self):
        self.complete('ERROR', errors=1, error_code='SYNTHETIC_SEARCH_FAILED')
        self.assertEqual(self.window.result.state, 'ERROR')
        self.assertEqual(self.window.result.error_code, 'SYNTHETIC_SEARCH_FAILED')
        self.assertEqual([r['ma_ho_so'] for r in self.window.model.rows], ['october'])
        self.assertIn("href='issues'", self.window.status.text())
        self.assertNotIn('Đã hoàn tất', self.window.status.text())

    def test_catalog_refresh_failure_cannot_claim_success_or_replace_view(self):
        previous = list(self.window.model.rows)
        broken = JobResult('ERROR', 'SYNTHETIC_CATALOG_READ_FAILED', self.folder)
        with patch('desktop.v2_interactions.catalog_view', return_value=broken):
            self.complete(rows=[self.row('incoming', '05/10/2026')], discovered=1)
        self.assertEqual(self.window.model.rows, previous)
        self.assertEqual(self.window.last_task.state, 'PARTIAL')
        self.assertIn('SYNTHETIC_CATALOG_READ_FAILED', self.window.status.toolTip())
        self.assertIn("href='issues'", self.window.status.text())

    def test_empty_success_is_confirmed_query_not_unqueried_local_view(self):
        self.period(8)
        self.window.active_config = self.window.make_config('tax', True)
        self.window.on_completed(JobResult('SUCCESS', 'No results', self.folder, account_key=ACCOUNT,
                                          date_range=('01/08/2026', '28/08/2026'), operation='query'))
        self.assertEqual(self.window.result.state, 'SUCCESS')
        self.assertIn('Không tìm thấy', self.window.empty.text())
        self.assertNotIn('bấm Tra cứu', self.window.empty.text())

    def test_late_job_identifies_requested_and_visible_periods(self):
        self.window.active_config = self.window.make_config('tax', False)
        self.period(9)
        self.window.on_completed(JobResult('SUCCESS', 'Done', self.folder, account_key=ACCOUNT,
                                          date_range=('01/10/2026', '28/10/2026'), operation='query_and_download'))
        self.assertEqual([r['ma_ho_so'] for r in self.window.model.rows], ['september'])
        self.assertIn('01/10/2026', self.window.status.text())
        self.assertIn('01/09/2026', self.window.status.text())
        self.assertEqual(self.window.result.operation, 'library')

    def test_partial_catalog_read_is_visible_and_preserves_job_error(self):
        selected = catalog_view(self.root, USERNAME, 'tax', '01/10/2026', '28/10/2026')
        selected.state, selected.message = 'PARTIAL', 'SYNTHETIC_ONE_FOLDER_FAILED'
        with patch('desktop.v2_interactions.catalog_view', return_value=selected):
            self.complete(discovered=1)
        self.assertEqual(self.window.last_task.state, 'PARTIAL')
        self.assertEqual(self.window.result.state, 'PARTIAL')
        self.assertGreater(self.window.result.errors, 0)
        self.assertIn('SYNTHETIC_ONE_FOLDER_FAILED', self.window.status.toolTip())
        self.assertIn("href='issues'", self.window.status.text())

    def test_progress_128_is_not_presented_as_known_total_and_finalize_is_visible(self):
        self.window.active_config = self.window.make_config('tax', False)
        self.window.on_progress({'record': self.row('progress', '05/10/2026'),
                                 'discovered': 128, 'downloaded': 128, 'errors': 0})
        self.assertNotIn('128/128', self.window.status.text())
        self.assertIn('128', self.window.status.text())
        self.window.on_progress({'stage': 'finalize'})
        self.assertIn('hoàn tất danh mục', self.window.status.text())
        self.complete(discovered=128, downloaded=128)
        self.assertIn('hoàn tất', self.window.status.text())
        self.assertIsNone(self.window.active_config)

    def test_filters_remain_visible_in_completion_summary(self):
        self.window.search.setText('synthetic-does-not-match')
        self.complete(discovered=1)
        self.assertIn('Đang lọc: 0/1', self.window.status.text())
        self.assertEqual(self.window.search.text(), 'synthetic-does-not-match')

    def test_running_download_refreshes_catalog_before_completion_at_128(self):
        from PySide6.QtTest import QTest

        self.window.active_config = self.window.make_config('tax', False)
        incoming = [self.row(f'new-{i}', '05/10/2026') for i in range(128)]
        self.catalog.upsert_documents('tax', incoming)
        for index, row in enumerate(incoming, 1):
            self.window.on_progress({'record': row, 'discovered': index, 'downloaded': index})
        self.assertTrue(self.window.catalog_refresh_timer.isActive())
        QTest.qWait(350)
        self.assertEqual(len(self.window.model.rows), 129)
        self.assertIn('Kho: 130', self.window.counts.text())
        self.assertIn('Kỳ đang xem: 129', self.window.counts.text())
        self.assertIsNotNone(self.window.active_config)

    def test_running_query_refreshes_small_repeated_batch_after_saved_view(self):
        from PySide6.QtTest import QTest

        saved = self.row('saved-folder', '05/10/2026')
        self.window.result = JobResult('LOADED', 'Saved', self.root / 'old-folder',
                                       rows=[saved], operation='saved')
        self.window.model.reset('tax', [saved])
        self.window.active_config = self.window.make_config('tax', True)
        row = self.row('october', '05/10/2026')
        for label in ('Updated once', 'Updated twice'):
            row['to_khai'] = label
            self.catalog.upsert_documents('tax', [row])
            self.window.on_progress({'record': row, 'discovered': 1, 'downloaded': 0})
            QTest.qWait(350)
            self.assertEqual(len(self.window.model.rows), 1)
            self.assertEqual(self.window.model.rows[0]['to_khai'], label)
            self.assertEqual(len(self.window.pending_rows), 1)

    def test_completion_stops_pending_refresh_and_keeps_completion_status(self):
        from PySide6.QtTest import QTest

        self.window.active_config = self.window.make_config('tax', False)
        self.window.on_progress({'record': self.row('october', '05/10/2026'),
                                 'discovered': 1, 'downloaded': 1})
        self.assertTrue(self.window.catalog_refresh_timer.isActive())
        self.complete(discovered=1)
        status = self.window.status.text()
        self.assertFalse(self.window.catalog_refresh_timer.isActive())
        QTest.qWait(350)
        self.assertEqual(self.window.status.text(), status)
        self.assertEqual(self.window.result.state, 'SUCCESS')

    def test_empty_online_result_does_not_claim_saved_rows_are_absent(self):
        self.complete(discovered=0)
        self.assertEqual([r['ma_ho_so'] for r in self.window.model.rows], ['october'])
        self.assertIn('Online không trả hồ sơ', self.window.status.text())
        self.assertIn('hồ sơ đã lưu', self.window.status.text())

    def test_query_after_viewing_saved_folder_refreshes_owned_catalog(self):
        saved = self.row('saved-folder', '05/10/2026')
        self.window.result = JobResult('LOADED', 'Saved', self.root / 'old-folder',
                                       rows=[saved], operation='saved')
        self.window.model.reset('tax', [saved])
        self.complete(discovered=1)
        self.assertEqual([r['ma_ho_so'] for r in self.window.model.rows], ['october'])
        self.assertEqual(self.window.last_task.state, 'SUCCESS')


if __name__ == '__main__':
    unittest.main()
