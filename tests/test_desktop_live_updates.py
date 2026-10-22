"""Incremental progress keeps identities, proxy indexes and queued UI updates safe."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from tests.support import cleanup_temporary_directory

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class LiveUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def row(case, **extra):
        return {'ma_ho_so': case, 'nguon': 'DVC', 'to_khai': 'Tờ khai GTGT',
                '_file_status': 'not_downloaded', **extra}

    def test_update_keeps_checked_rows_and_persistent_source_indexes(self):
        from PySide6.QtCore import QPersistentModelIndex

        from desktop.documents import document_id
        from desktop.table_model import RecordsModel
        model = RecordsModel()
        model.reset('tax', [self.row('A'), self.row('B')])
        model.checked.add(document_id('tax', model.rows[1]))
        index = QPersistentModelIndex(model.index(1, 1))
        reset = Mock()
        model.modelReset.connect(reset)
        model.upsert_many([self.row('A', _file_status='downloaded'),
                           self.row('B', to_khai='Tên đã cập nhật'), self.row('C')])
        self.assertTrue(index.isValid())
        self.assertEqual(index.data(), 'Tên đã cập nhật')
        self.assertEqual(model.checked, {document_id('tax', model.rows[1])})
        self.assertEqual(model.rowCount(), 3)
        reset.assert_not_called()

    def test_source_scoping_and_duplicate_burst_do_not_duplicate_records(self):
        from desktop.table_model import RecordsModel
        model = RecordsModel()
        model.reset('tax', [self.row('A')])
        inserted = Mock()
        model.rowsInserted.connect(inserted)
        model.upsert_many([self.row('A', _file_status='downloaded'),
                           self.row('A', nguon='ETAX_LEGACY'),
                           self.row('A', nguon='ETAX_LEGACY', to_khai='Legacy updated'),
                           self.row('B')])
        self.assertEqual(model.rowCount(), 3)
        self.assertEqual(model.rows[0]['_file_status'], 'downloaded')
        self.assertEqual(model.rows[1]['to_khai'], 'Legacy updated')
        self.assertEqual(inserted.call_count, 1)
        model.upsert_many([self.row('B', _file_status='failed')])
        self.assertEqual(model.rowCount(), 3)
        self.assertEqual(model.rows[2]['_file_status'], 'failed')

    def test_proxy_rechecks_search_status_and_sort_after_updates(self):
        from PySide6.QtCore import Qt

        from desktop.table_model import RecordsModel, RecordsProxy
        model, proxy = RecordsModel(), RecordsProxy()
        proxy.setSourceModel(model)
        model.reset('tax', [self.row('A', ngay_nop='01/10/2026'),
                            self.row('B', ngay_nop='02/10/2026')])
        proxy.sort(3, Qt.SortOrder.DescendingOrder)
        proxy.setFilterFixedString('new name')
        proxy.set_status_filter('downloaded')
        self.assertEqual(proxy.rowCount(), 0)
        model.upsert_many([self.row('A', to_khai='New name', _file_status='downloaded',
                                    ngay_nop='22/10/2026')])
        self.assertEqual(proxy.rowCount(), 1)
        self.assertEqual(proxy.index(0, 1).data(), 'New name')
        proxy.setFilterFixedString('')
        proxy.set_status_filter('all')
        self.assertEqual(proxy.index(0, 3).data(), '22/10/2026')

    def test_progress_burst_flushes_once_and_completion_stops_stale_timer(self):
        from desktop.documents import document_id
        from desktop.services import JobResult, RunConfig
        from desktop.settings_store import Preferences, SettingsStore
        from desktop.ui import MainWindow
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(cleanup_temporary_directory, temporary)
        root = Path(temporary.name)
        store = SettingsStore(root / 'settings.json')
        store.save(Preferences(output=str(root)))
        window = MainWindow(store)
        self.addCleanup(window.close)
        first = self.row('selected')
        window.model.reset('tax', [first])
        window.model.checked.add(document_id('tax', first))
        window.pending_rows = {document_id('tax', first): first}
        window.active_config = RunConfig('tax', root, dry_run=True)
        reset, inserted = Mock(), Mock()
        window.model.modelReset.connect(reset)
        window.model.rowsInserted.connect(inserted)
        for index in range(500):
            window.on_progress({'record': self.row(str(index)), 'discovered': index + 1})
        self.assertEqual(window.model.rowCount(), 1)
        self.assertTrue(window.progress_flush.isActive())
        window.flush_progress_rows()
        self.assertEqual(window.model.rowCount(), 501)
        self.assertEqual(inserted.call_count, 1)
        self.assertIn(document_id('tax', first), window.model.checked)
        reset.assert_not_called()
        result = JobResult('CANCELLED', 'Stopped', root, rows=list(window.model.rows))
        window.on_completed(result)
        self.assertFalse(window.progress_flush.isActive())
        self.assertFalse(window.progress_updates)
        self.app.processEvents()
        self.assertEqual(window.model.rowCount(), 501)


if __name__ == '__main__':
    unittest.main()
