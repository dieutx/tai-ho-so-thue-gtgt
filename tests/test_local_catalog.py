"""Persistent inventory and real pipeline smart-sync contracts, synthetic data only."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import patch

from desktop.documents import verify_rows
from desktop.library import catalog_view, check_files, load_library
from desktop.services import RunConfig, run_online
from desktop.settings_store import Preferences, SettingsStore
from desktop.state import job_output
from gdt_tax.gnt.models import GiayNopTien, GntPageResult
from gdt_tax.gnt.storage import GntStore
from gdt_tax.identity import AttachmentKey, IdentityError, account_fingerprint
from gdt_tax.local_catalog import LocalCatalog
from gdt_tax.models import CaseRecord
from gdt_tax.ownership import check_owner
from gdt_tax.run_hooks import RunHooks
from tests.support import FakeHttp, StubCaptcha, cleanup_temporary_directory, fixture, sample_zip

ACCOUNT = account_fingerprint('synthetic-catalog-owner')


def row(number, day='05/10/2026', source='DVC', account=ACCOUNT):
    return CaseRecord(str(number), source, account_key=account, ngay_nop=day,
                      ky_tinh_thue='10/2026', to_khai='Tờ khai bổ sung').to_dict()


class LocalCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = LocalCatalog(self.root / 'owned', ACCOUNT)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def test_repeated_100_to_105_and_restart_keeps_inventory(self):
        rows = [row(i) for i in range(100)]
        self.catalog.upsert_documents('tax', rows)
        for _ in range(100):
            self.catalog.upsert_documents('tax', rows)
        self.assertEqual(self.catalog.get_counts('tax')['total'], 100)
        self.catalog.upsert_documents('tax', [row(i) for i in range(105)])
        reopened = LocalCatalog(self.catalog.root, ACCOUNT)
        self.assertEqual(reopened.get_counts('tax')['total'], 105)
        self.assertEqual(reopened.integrity_check(), 'ok')

    def test_multiple_years_boundary_filter_and_unknown_dates(self):
        self.catalog.upsert_documents('tax', [row('old', '31/12/2025'), row('start', '01/10/2026'),
                                             row('end', '31/10/2026 10:30'), row('unknown', 'bad')])
        self.assertEqual(len(self.catalog.get_documents('tax', '01/10/2026', '31/10/2026')), 2)
        self.assertEqual(len(self.catalog.get_documents('tax', '01/01/2025', '31/12/2025')), 1)
        self.assertEqual(len(self.catalog.get_documents('tax', unknown=True)), 1)
        self.assertEqual(self.catalog.get_counts('tax')['total'], 4)
        with self.assertRaises(ValueError):
            self.catalog.get_documents('tax', "'; DROP TABLE documents;--")

    def test_source_kind_account_and_supplemental_isolation(self):
        self.catalog.upsert_documents('tax', [row('same'), row('same', source='ETAX_LEGACY'), row('supplemental')])
        self.catalog.upsert_documents('gnt', [GiayNopTien('same', account_key=ACCOUNT).to_dict()])
        rejected = self.catalog.upsert_documents('tax', [row('other', account=account_fingerprint('other'))])
        self.assertEqual(rejected['quarantined'], 1)
        self.assertEqual(self.catalog.get_counts('tax')['total'], 3)
        self.assertEqual(self.catalog.get_counts('gnt')['total'], 1)
        with self.assertRaises(IdentityError):
            LocalCatalog(self.catalog.root, account_fingerprint('other'))

    def test_conflicting_identity_unknown_owner_and_path_escape_quarantined(self):
        conflicting = dict(row('one'), ma_ho_so='two')
        unknown = dict(row('unknown'), account_key='UNKNOWN', record_key='')
        traversal = dict(row('escape'), tep_zip='../outside.zip')
        result = self.catalog.upsert_documents('tax', [conflicting, unknown, traversal])
        self.assertEqual(result['quarantined'], 3)
        self.assertEqual(self.catalog.get_counts('tax')['total'], 0)

    def test_empty_online_does_not_delete_and_empty_fields_keep_evidence(self):
        original = dict(row("x'; DROP TABLE documents;--"), trang_thai='Đã chấp nhận', tep_zip='x.zip',
                        _file_status='downloaded', _file_hash='synthetic-digest', _file_size=5)
        self.catalog.upsert_documents('tax', [original])
        self.catalog.upsert_documents('tax', [dict(original, trang_thai='', tep_zip='', _file_hash='', _file_status='not_downloaded')])
        self.catalog.upsert_documents('tax', [], online=True)
        saved = self.catalog.get_documents('tax')[0]
        self.assertEqual(saved['trang_thai'], 'Đã chấp nhận')
        self.assertEqual(saved['tep_zip'], 'x.zip')
        self.assertEqual(saved['_file_hash'], 'synthetic-digest')
        self.catalog.upsert_documents('tax', [dict(original, _integrity_status='invalid')])
        with self.catalog.connection() as db:
            self.assertEqual(db.execute('SELECT verification_state FROM artifacts').fetchone()[0], 'invalid')

    def test_transaction_rolls_back_and_backup_restores(self):
        self.catalog.upsert_documents('tax', [row('good')])
        with self.assertRaises(RuntimeError), self.catalog.connection() as db:
            db.execute('UPDATE documents SET raw_metadata_json=?', ('{}',))
            raise RuntimeError('simulated crash')
        self.assertEqual(self.catalog.get_documents('tax')[0]['ma_ho_so'], 'good')
        backup = self.catalog.backup()
        from contextlib import closing
        with closing(sqlite3.connect(backup)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0], 1)

    def test_migration_dry_run_idempotent_and_file_bytes_unchanged(self):
        path = self.catalog.root / 'original.zip'
        path.write_bytes(sample_zip())
        source = self.catalog.root / 'danh_sach_ho_so.json'
        source.write_text(json.dumps([dict(row('old', '01/06/2025'), tep_zip=path.name), row('new')]), encoding='utf-8')
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, path)}
        preview = self.catalog.import_json('tax', dry_run=True)
        self.assertEqual(preview['new'], 2)
        self.assertEqual(self.catalog.get_counts('tax')['total'], 0)
        imported = self.catalog.import_json('tax')
        self.assertEqual(imported['new'], 2)
        self.assertEqual(self.catalog.import_json('tax')['state'], 'ALREADY_IMPORTED')
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, path)})

    def test_attachments_are_separate_and_wrong_parent_requires_review(self):
        primary = row('parent')
        parent = CaseRecord('parent', 'DVC', account_key=ACCOUNT).key
        good = AttachmentKey(parent, 'DVC', 'receipt').serialize()
        wrong = AttachmentKey(CaseRecord('other', 'DVC', account_key=ACCOUNT).key, 'DVC', 'wrong').serialize()
        primary['_notices'] = [{'reference_key': good, 'path': 'receipt.xml', 'reference_status': 'INVALID'},
                               {'reference_key': wrong, 'path': 'other.xml'}]
        self.catalog.upsert_documents('tax', [primary])
        with self.catalog.connection() as db:
            artifact = db.execute('SELECT artifact_role,verification_state FROM artifacts').fetchone()
        self.assertEqual(tuple(artifact), ('attachment', 'invalid'))
        self.assertEqual(self.catalog.get_counts('tax')['quarantined'], 1)

    def test_unknown_legacy_folder_is_never_adopted(self):
        folder = self.root / 'unowned'
        folder.mkdir()
        (folder / 'old.zip').write_bytes(sample_zip())
        with self.assertRaisesRegex(IdentityError, 'LEGACY_UNOWNED'):
            LocalCatalog(folder, ACCOUNT)
        self.assertFalse((folder / '.gdt-owner.json').exists())

    def test_local_view_no_network_no_deep_hash_and_missing_file_detected(self):
        username = 'synthetic-catalog-owner'
        folder = job_output(self.root, username, 'tax')
        catalog = LocalCatalog(folder, ACCOUNT)
        record = CaseRecord('saved', 'DVC', account_key=ACCOUNT, ngay_nop='05/10/2026')
        from gdt_tax.storage import ZipStore
        path = ZipStore(folder).save(record, sample_zip())
        verified = verify_rows('tax', [record.to_dict()], folder)
        catalog.upsert_documents('tax', verified)
        with patch('requests.sessions.Session.request', side_effect=AssertionError('network')), patch(
                'desktop.documents.read_bounded', side_effect=AssertionError('deep verify')):
            result = catalog_view(self.root, username, 'tax', '01/10/2026', '31/10/2026')
            self.assertEqual(result.rows[0]['_file_status'], 'downloaded')
            path.unlink()
            result = catalog_view(self.root, username, 'tax', '01/10/2026', '31/10/2026')
            self.assertEqual(result.rows[0]['_file_status'], 'not_downloaded')
            self.assertEqual(result.inventory_total, 1)

    def test_unverified_or_modified_file_is_not_green(self):
        folder = self.catalog.root
        (folder / 'bad.zip').write_bytes(b'broken')
        self.assertEqual(check_files('tax', [dict(row('bad'), tep_zip='bad.zip')], folder)[0]['_file_status'], 'not_downloaded')

    def test_sync_history_never_changes_inventory(self):
        self.catalog.upsert_documents('tax', [row(1)])
        run = self.catalog.start_sync_run('tax', '01/10/2026', '31/10/2026', 'query')
        self.catalog.finish_sync_run(run, 'PARTIAL', {'errors': 1})
        self.assertEqual(self.catalog.get_counts('tax')['total'], 1)
        with self.catalog.connection() as db:
            self.assertEqual(db.execute('SELECT state FROM sync_runs').fetchone()[0], 'PARTIAL')

    def test_hard_process_exit_rolls_back_uncommitted_write(self):
        self.catalog.upsert_documents('tax', [row('committed')])
        code = ("import os,sqlite3,sys; db=sqlite3.connect(sys.argv[1]); "
                "db.execute('BEGIN IMMEDIATE'); db.execute('UPDATE documents SET raw_metadata_json=?', ('{}',)); os._exit(7)")
        crashed = subprocess.run([sys.executable, '-c', code, str(self.catalog.path)], capture_output=True, timeout=15)
        self.assertEqual(crashed.returncode, 7)
        reopened = LocalCatalog(self.catalog.root, ACCOUNT)
        self.assertEqual(reopened.get_documents('tax')[0]['ma_ho_so'], 'committed')
        self.assertEqual(reopened.integrity_check(), 'ok')

    def test_metrics_are_bounded_and_do_not_store_endpoint_or_secret(self):
        from gdt_tax.metrics import HttpMetrics
        from gdt_tax.run_hooks import RunBudget
        metrics = HttpMetrics()
        for _ in range(2100):
            metrics.record('sensitive-endpoint', 200, .01, 10)
        summary = metrics.snapshot()
        self.assertEqual(summary['requests'], 2100)
        self.assertEqual(summary['latency_sample_count'], 2048)
        self.assertNotIn('sensitive-endpoint', json.dumps(summary))
        budget = RunBudget(max_records=5)
        for _ in range(5):
            budget.record()
        from gdt_tax.run_hooks import RunCancelled
        with self.assertRaises(RunCancelled):
            budget.record()


class IncrementalPipelineTests(unittest.TestCase):
    def test_import_evidence_conflict_does_not_copy_primary_or_overwrite_evidence(self):
        from desktop.migration import _copy_artifact
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.mkdir()
            target.mkdir()
            document = source / 'record.xml'
            document.write_bytes(b'<record/>')
            document.with_name('record.xml.integrity.json').write_bytes(b'source evidence')
            evidence = target / 'record.xml.integrity.json'
            evidence.write_bytes(b'existing evidence')
            with self.assertRaisesRegex(ValueError, 'khác nguồn'):
                _copy_artifact(source, target, document)
            self.assertFalse((target / 'record.xml').exists())
            self.assertEqual(evidence.read_bytes(), b'existing evidence')
            self.assertEqual(document.read_bytes(), b'<record/>')

    def test_trusted_import_preserves_attachments_and_original_manifest(self):
        from desktop.migration import load_saved
        from desktop.notices import read_notices
        from gdt_tax.dvc_notices import NOTICE_DIRECTORY, DvcNotice, NoticeFile, NoticeStore
        from gdt_tax.storage import ZipStore, write_metadata
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            check_owner(source, ACCOUNT, create=True)
            record = CaseRecord('attachment-import', 'DVC', account_key=ACCOUNT)
            ZipStore(source).save(record, sample_zip())
            payload = NoticeFile('notice.xml', b'<TBaoThueDTu><TBaoThue/></TBaoThueDTu>', 'xml')
            NoticeStore(source / NOTICE_DIRECTORY).save(record.key, DvcNotice('receipt'), payload)
            write_metadata(source, [record])
            before = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in source.rglob('*') if p.is_file()}
            config = RunConfig('import', target, username='synthetic-catalog-owner', source=source, stage='tax')
            result = load_saved(config, RunHooks(), copy_files=True)
            self.assertEqual(result.state, 'SUCCESS')
            notices = read_notices(target, record.ma_ho_so, parent_key=record.record_key)
            self.assertEqual(len(notices), 1)
            self.assertEqual(notices[0]['reference_status'], 'VERIFIED')
            after = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in source.rglob('*') if p.is_file()}
            self.assertEqual(before, after)

    def test_explicit_import_requires_owner_and_persists_trusted_records(self):
        from desktop.migration import load_saved
        from gdt_tax.gnt.storage import write_gnt_metadata
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            check_owner(source, ACCOUNT, create=True)
            record = GiayNopTien('trusted-import', ngay_lap='05/10/2026', account_key=ACCOUNT)
            path = GntStore(source).save(record, fixture('gnt_chungtu.xml').encode())
            write_gnt_metadata(source, [record])
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            config = RunConfig('import', target, username='synthetic-catalog-owner', source=source, stage='gnt')
            result = load_saved(config, RunHooks(), copy_files=True)
            self.assertEqual(result.state, 'SUCCESS')
            self.assertEqual(LocalCatalog(target, ACCOUNT).get_counts('gnt')['total'], 1)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            checked = verify_rows('gnt', result.rows, target)
            self.assertEqual(checked[0]['_file_status'], 'downloaded')

    def test_100_to_105_reuses_98_downloads_exactly_seven_then_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            username = 'synthetic-catalog-owner'
            check_owner(folder, ACCOUNT, create=True)
            records = [GiayNopTien(str(i), so_gnt=str(i), ngay_lap='05/10/2026', account_key=ACCOUNT) for i in range(105)]
            xml = fixture('gnt_chungtu.xml').encode()
            store = GntStore(folder)
            for record in records[:98]:
                store.save(record, xml)
            catalog = LocalCatalog(folder, ACCOUNT)
            catalog.upsert_documents('gnt', [record.to_dict() for record in records[:100]])
            downloads = []

            class Portal:
                def search_gnt(self, period, page):
                    return GntPageResult([replace(record) for record in records], 1, 200)

                def download_gnt(self, record):
                    downloads.append(record.ctu_id)
                    return xml

            config = RunConfig('gnt', folder, username=username, password='synthetic-secret',
                               from_date='01/10/2026', to_date='07/10/2026',
                               preferences=Preferences(record_delay=0, page_delay=0, jitter=0))
            result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('test'),
                                http=FakeHttp(lambda *_args: None), portal_factory=Portal)
            self.assertEqual(result.state, 'SUCCESS', result.message)
            self.assertEqual(downloads, [str(i) for i in range(98, 105)])
            self.assertEqual(result.reused, 98)
            self.assertEqual(result.sync_metrics['new'], 5)
            self.assertEqual(catalog.get_counts('gnt')['total'], 105)
            downloads.clear()
            again = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('test'),
                               http=FakeHttp(lambda *_args: None), portal_factory=Portal)
            self.assertEqual(downloads, [])
            self.assertEqual(again.reused, 105)

    def test_cancel_after_discovery_commits_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            stop = Event()

            class Portal:
                def search_gnt(self, period, page):
                    return GntPageResult([GiayNopTien('first', ngay_lap='05/10/2026')], 1, 200)

                def download_gnt(self, record):
                    self_outer.assertEqual(LocalCatalog(folder, ACCOUNT).get_counts('gnt')['total'], 1)
                    stop.set()
                    return None

            self_outer = self
            config = RunConfig('gnt', folder, username='synthetic-catalog-owner', password='synthetic-secret',
                               from_date='01/10/2026', to_date='07/10/2026', preferences=Preferences(record_delay=0))
            result = run_online(config, RunHooks(stop), StubCaptcha(), logging.getLogger('test'),
                                http=FakeHttp(lambda *_args: None), portal_factory=Portal)
            self.assertEqual(result.state, 'CANCELLED')
            self.assertEqual(LocalCatalog(folder, ACCOUNT).get_counts('gnt')['total'], 1)


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Optional desktop Qt dependencies')
class PersistentUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.ui import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = MainWindow(SettingsStore(self.root / 'settings.json'))
        self.window.output.setText(str(self.root))
        self.window.controller.sessions.set_account('synthetic-catalog-owner', '')
        folder = job_output(self.root, 'synthetic-catalog-owner', 'tax')
        self.catalog = LocalCatalog(folder, ACCOUNT)
        self.catalog.upsert_documents('tax', [row('2025', '05/06/2025'), row('2026'), row('unknown', '')])

    def tearDown(self):
        self.window.close()
        cleanup_temporary_directory(self.temp)

    def period(self, year, month):
        from PySide6.QtCore import QDate
        self.window.applying_preset = True
        self.window.from_date.setDate(QDate(year, month, 1))
        self.window.to_date.setDate(QDate(year, month, 28))
        self.window.applying_preset = False
        self.window.dates_changed()

    def test_switch_years_no_http_restart_and_unknown_date_group(self):
        self.assertFalse(hasattr(self.window, 'unknown_dates'))
        with patch('requests.sessions.Session.request', side_effect=AssertionError('unexpected HTTP')):
            for year, month in [(2025, 6), (2026, 10), (2025, 6)]:
                self.period(year, month)
                names = {row['ma_ho_so'] for row in self.window.model.rows}
                # Hồ sơ thiếu ngày vẫn hiện với ngày "—", không bị bỏ âm thầm.
                self.assertEqual(names, {str(year), 'unknown'})
                self.assertEqual(self.catalog.get_counts('tax')['total'], 3)
        self.window.save_tab()
        restored = self.window._restore_tab_state('tax')
        self.assertEqual(restored.from_date, '01/06/2025')
        self.window.controller.sessions.set_account('other', '')
        self.window.clear_account_views()
        self.assertEqual(self.window.model.rows, [])

    def test_form_stays_visible_after_completion_and_late_job_keeps_current_period(self):
        from desktop.services import JobResult
        self.period(2025, 6)
        config = self.window.make_config('tax', True)
        self.window.active_config = config
        self.period(2026, 10)
        self.window.on_completed(JobResult('SUCCESS', 'Done', config.output, account_key=ACCOUNT,
                                          date_range=('01/06/2025', '28/06/2025'), operation='query'))
        self.assertEqual(self.window.from_date.date().year(), 2026)
        self.assertEqual(self.window.model.rows[0]['ma_ho_so'], '2026')
        self.assertFalse(self.window.config_panel.isHidden())
        self.assertFalse(hasattr(self.window, 'edit_conditions'))
        self.assertEqual(self.catalog.get_counts('tax')['total'], 3)

    def test_query_and_download_keep_dates_and_controls_for_every_completion_state(self):
        from desktop.services import JobResult
        for mode in ('tax', 'gnt', 'notice'):
            self.window.mode_changed(('tax', 'gnt', 'notice').index(mode))
            for query_only in (True, False):
                for state in ('SUCCESS', 'PARTIAL', 'ERROR', 'CANCELLED'):
                    with self.subTest(mode=mode, query_only=query_only, state=state):
                        self.period(2026, 10)
                        config = self.window.make_config(mode, query_only)
                        self.window.active_config = config
                        before = (self.window.from_date.date(), self.window.to_date.date(),
                                  self.window.preset.currentData())
                        self.window.on_completed(JobResult(state, 'Synthetic completion', config.output,
                                                           account_key=ACCOUNT))
                        self.assertEqual((self.window.from_date.date(), self.window.to_date.date(),
                                          self.window.preset.currentData()), before)
                        for widget in (self.window.config_panel, self.window.from_date,
                                       self.window.to_date, self.window.preset, self.window.query,
                                       self.window.start_button):
                            self.assertFalse(widget.isHidden())
                        self.assertFalse(hasattr(self.window, 'edit_conditions'))
        self.assertEqual(self.catalog.get_counts('tax')['total'], 3)

    def test_library_worker_import_preserves_known_periods(self):
        config = RunConfig('library', self.root, username='synthetic-catalog-owner',
                           from_date='01/06/2025', to_date='30/06/2025')
        result = load_library(config, RunHooks())
        self.assertEqual(result.children['tax'].inventory_total, 3)
        self.assertEqual(len(result.children['tax'].rows), 1)

    def test_reopen_starts_recent30_and_keeps_older_rows_available(self):
        from PySide6.QtCore import QDate

        from desktop.ui import MainWindow
        self.period(2025, 6)
        self.window.save_tab()
        self.window.preferences.account_type = 'CN'
        self.window.store.save(self.window.preferences)
        reopened = MainWindow(SettingsStore(self.root / 'settings.json'))
        try:
            self.assertEqual(reopened.account_type.currentData(), 'DN')
            reopened.output.setText(str(self.root))
            reopened.controller.sessions.set_account('synthetic-catalog-owner', '')
            reopened.clear_account_views()
            reopened.apply_local_date_filter()
            today = QDate.currentDate()
            self.assertEqual(reopened.from_date.date(), today.addDays(-29))
            self.assertEqual(reopened.to_date.date(), today)
            self.assertEqual(reopened.preset.currentData(), 'recent30')
            self.assertNotIn('2025', {row['ma_ho_so'] for row in reopened.model.rows})
            reopened.from_date.setDate(QDate(2025, 6, 1))
            reopened.to_date.setDate(QDate(2025, 6, 28))
            self.assertEqual(reopened.model.rows[0]['ma_ho_so'], '2025')
        finally:
            reopened.close()


if __name__ == '__main__':
    unittest.main()
