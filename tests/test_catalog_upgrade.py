"""Cập nhật app không bắt tải lại: database nâng cấp tại chỗ và giữ hồ sơ đã tải."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gdt_tax import local_catalog
from gdt_tax.identity import account_fingerprint
from gdt_tax.local_catalog import LocalCatalog
from tests.support import cleanup_temporary_directory

USERNAME = 'synthetic-upgrade-owner'
ACCOUNT = account_fingerprint(USERNAME)


class CatalogUpgradeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def seed(self) -> Path:
        """Tạo database như bản app trước, kèm tệp đã tải trên máy."""
        catalog = LocalCatalog(self.root, ACCOUNT)
        archive = self.root / 'ho-so-1.zip'
        archive.write_bytes(b'PK synthetic archive')
        catalog.upsert_documents('tax', [{
            'ma_ho_so': '1', 'nguon': 'DVC', 'account_key': ACCOUNT,
            'ngay_nop': '05/10/2026', 'to_khai': '01/GTGT',
            '_file_status': 'downloaded', '_file_path': str(archive),
            '_file_size': archive.stat().st_size, '_file_hash': 'abc'}])
        return archive

    def test_schema_upgrade_keeps_downloaded_rows_and_files(self):
        archive = self.seed()
        migration = (2, 'ALTER TABLE documents ADD COLUMN ui_hint TEXT;')
        with patch.object(local_catalog, 'SCHEMA_VERSION', 2), \
                patch.object(local_catalog, 'MIGRATIONS', (migration,)):
            upgraded = LocalCatalog(self.root, ACCOUNT)
            rows = upgraded.get_documents('tax', '01/10/2026', '31/10/2026')
        self.assertEqual([row['ma_ho_so'] for row in rows], ['1'])
        self.assertEqual(rows[0]['_file_status'], 'downloaded')
        self.assertEqual(Path(rows[0]['_file_path']).resolve(), archive.resolve())
        self.assertTrue(archive.is_file())
        database = sqlite3.connect(self.root / 'catalog.sqlite3')
        try:
            self.assertEqual(database.execute('PRAGMA user_version').fetchone()[0], 2)
            versions = [row[0] for row in database.execute('SELECT version FROM schema_migrations ORDER BY version')]
        finally:
            database.close()
        self.assertEqual(versions, [1, 2])
        self.assertTrue(list(self.root.glob('catalog.backup-*.sqlite3')))

    def test_reopening_same_version_does_not_rewrite_or_backup(self):
        self.seed()
        database = self.root / 'catalog.sqlite3'
        before = database.read_bytes()
        catalog = LocalCatalog(self.root, ACCOUNT)
        self.assertEqual(catalog.get_counts('tax')['total'], 1)
        self.assertEqual(database.read_bytes(), before)
        self.assertFalse(list(self.root.glob('catalog.backup-*.sqlite3')))

    def test_newer_database_is_refused_without_touching_bytes(self):
        self.seed()
        database = self.root / 'catalog.sqlite3'
        connection = sqlite3.connect(database)
        connection.execute('PRAGMA user_version=99')
        connection.commit()
        connection.close()
        before = database.read_bytes()
        with self.assertRaises(ValueError):
            LocalCatalog(self.root, ACCOUNT)
        self.assertEqual(database.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
