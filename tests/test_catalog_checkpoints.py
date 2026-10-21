"""Real process writers and injected crash/disk/lock faults; synthetic rows only."""
from __future__ import annotations

import errno
import json
import multiprocessing
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from gdt_tax.catalog import CatalogCheckpoint, catalog_lock, reports_current
from gdt_tax.config import Settings
from gdt_tax.errors import StorageError
from gdt_tax.identity import account_fingerprint
from gdt_tax.models import CaseRecord
from gdt_tax.ownership import prepare_output
from gdt_tax.pipeline import Pipeline
from gdt_tax.rebuild_reports import rebuild
from gdt_tax.run_hooks import RunCancelled, RunHooks
from gdt_tax.storage import ZipStore, write_metadata
from tests.support import FakeHttp, StubCaptcha, cleanup_temporary_directory, sample_zip
from tests.test_identity_integration import FixturePortal


def _writer(directory, prefix, ready):
    ready.wait(10)
    for index in range(10):
        write_metadata(directory, [CaseRecord(prefix + str(index), 'DVC')], materialize=False)


def _crash_writer(directory):
    with patch('gdt_tax.storage.write_excel_report', side_effect=lambda *_: os._exit(17)):
        write_metadata(directory, [CaseRecord('crash-committed', 'DVC')])


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = self.root / 'danh_sach_ho_so.json'

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def rows(self):
        return json.loads(self.catalog.read_bytes())

    def test_two_processes_do_not_lose_updates(self):
        context = multiprocessing.get_context('spawn')
        ready = context.Event()
        processes = [context.Process(target=_writer, args=(str(self.root), prefix, ready)) for prefix in ('a', 'b')]
        for process in processes:
            process.start()
        ready.set()
        for process in processes:
            process.join(30)
            if process.is_alive():
                process.terminate()
                self.fail('writer did not finish')
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(len(self.rows()), 20)

    def test_crash_between_catalog_and_workbook_recovers_generation_and_os_lock(self):
        write_metadata(self.root, [CaseRecord('previous', 'DVC')])
        context = multiprocessing.get_context('spawn')
        process = context.Process(target=_crash_writer, args=(str(self.root),))
        process.start()
        process.join(20)
        if process.is_alive():
            process.terminate()
            self.fail('crash fixture did not finish')
        self.assertEqual(process.exitcode, 17)
        self.assertEqual({row['ma_ho_so'] for row in self.rows()}, {'previous', 'crash-committed'})
        self.assertFalse(reports_current(self.catalog))
        write_metadata(self.root, [CaseRecord('recovered', 'DVC')])
        self.assertEqual(len(self.rows()), 3)
        self.assertTrue(reports_current(self.catalog))

    def test_disk_full_before_replace_keeps_previous_catalog(self):
        from gdt_tax.storage import _atomic_write
        write_metadata(self.root, [CaseRecord('previous', 'DVC')])
        before = self.catalog.read_bytes()
        def fail_catalog(path, data):
            if path == self.catalog:
                raise OSError(errno.ENOSPC, 'synthetic full disk')
            return _atomic_write(path, data)
        with patch('gdt_tax.storage._atomic_write', side_effect=fail_catalog):
            with self.assertRaises(OSError):
                write_metadata(self.root, [CaseRecord('incoming', 'DVC')])
        self.assertEqual(self.catalog.read_bytes(), before)
        self.assertTrue(reports_current(self.catalog))

    def test_locked_report_keeps_committed_catalog_and_marks_pending(self):
        write_metadata(self.root, [CaseRecord('previous', 'DVC')])
        workbook = self.root / 'danh_sach_to_khai.xlsx'
        original = workbook.read_bytes()
        with patch('gdt_tax.storage.write_excel_report', side_effect=PermissionError('synthetic Excel lock')):
            with self.assertRaises(PermissionError):
                write_metadata(self.root, [CaseRecord('incoming', 'DVC')])
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(workbook.read_bytes(), original)
        self.assertFalse(reports_current(self.catalog))
        write_metadata(self.root, [CaseRecord('incoming', 'DVC')])
        self.assertTrue(reports_current(self.catalog))

    def test_count_time_and_final_flush_bound_workbook_builds(self):
        now = [0.0]
        writer = Mock(return_value=('csv', 'json'))
        checkpoint = CatalogCheckpoint(writer, self.root, clock=lambda: now[0])
        records = {}
        for index in range(5000):
            records[str(index)] = index
            checkpoint.persist(records)
        checkpoint.persist(records, materialize=True)
        self.assertEqual(len(writer.call_args_list), 51)
        self.assertEqual(sum(call.kwargs['materialize'] for call in writer.call_args_list), 1)
        now[0] = 31
        checkpoint.persist(records)
        self.assertFalse(writer.call_args.kwargs['materialize'])

    def test_lock_timeout_is_bounded(self):
        with catalog_lock(self.root):
            with self.assertRaisesRegex(StorageError, 'CATALOG_BUSY'):
                with catalog_lock(self.root, timeout=0):
                    self.fail('second writer acquired exclusive lock')

    def test_uncheckpointed_valid_file_resumes_and_cancel_flushes(self):
        settings = Settings('synthetic', 'fake', date(2025, 7, 1), date(2025, 7, 1), self.root,
                            dvc_enabled=True, pause_between_records=0, pause_between_pages=0)
        prepare_output(settings)
        seed = CaseRecord('same-id', 'DVC', to_khai='synthetic declaration',
                          account_key=account_fingerprint('synthetic'))
        ZipStore(self.root).save(seed, sample_zip())
        downloads = []
        portal = FixturePortal('DVC', downloads)
        def cancel(**_):
            raise RunCancelled('synthetic controlled cancellation')
        hooks = RunHooks(progress=lambda _: cancel())
        pipeline = Pipeline(settings, FakeHttp(lambda *_: None), StubCaptcha(), hooks=hooks,
                            portal_factory=lambda *_: {'DVC': portal})
        with patch('gdt_tax.pipeline.login', return_value=True), patch('gdt_tax.pipeline.open_landing', return_value=''):
            with self.assertRaises(RunCancelled):
                pipeline.run()
        self.assertEqual(downloads, [])
        self.assertEqual(len(pipeline.reused_ids), 1)
        self.assertEqual(len(self.rows()), 1)
        self.assertTrue(reports_current(self.catalog))

    def test_rebuild_is_offline_and_preserves_extra_columns(self):
        write_metadata(self.root, [CaseRecord('previous', 'DVC')], materialize=False)
        rows = self.rows()
        rows[0]['custom_column'] = 'preserve'
        self.catalog.write_text(json.dumps(rows), encoding='utf-8')
        with patch('socket.socket.connect', side_effect=AssertionError('rebuild used network')):
            self.assertTrue(rebuild(self.catalog, 'DECLARATION'))
        self.assertEqual(self.rows()[0]['custom_column'], 'preserve')
