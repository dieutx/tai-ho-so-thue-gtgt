"""Synthetic ownership boundary and lossless legacy migration contracts."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from desktop.services import RunConfig
from desktop.sessions import ETaxSessionManager
from gdt_tax.config import Settings
from gdt_tax.gnt.pipeline import GntPipeline
from gdt_tax.identity import IdentityError, RecordKey, account_fingerprint
from gdt_tax.integrity import safe_destination, source_reference, validate_tax_zip, write_evidence
from gdt_tax.migrate_identity import migrate
from gdt_tax.models import CaseRecord
from gdt_tax.ownership import OWNER_NAME, check_owner
from gdt_tax.pipeline import Pipeline
from gdt_tax.tb.pipeline import TbPipeline
from tests.support import FakeHttp, StubCaptcha, cleanup_temporary_directory, sample_zip


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.account = account_fingerprint('synthetic-owner')

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def test_owner_repeat_and_cross_account_before_auth(self):
        check_owner(self.root, self.account, create=True)
        before = (self.root / OWNER_NAME).read_bytes()
        check_owner(self.root, self.account, create=True)
        self.assertEqual((self.root / OWNER_NAME).read_bytes(), before)
        for mode in ('tax', 'gnt', 'notice'):
            config = RunConfig(mode, self.root, username='different-account', password='fake-secret')
            manager = ETaxSessionManager()
            with patch.object(manager, 'ensure_authenticated') as authenticate:
                with self.assertRaisesRegex(IdentityError, 'DIRECTORY_ACCOUNT_MISMATCH'):
                    manager.execute(config, Mock(), StubCaptcha())
                authenticate.assert_not_called()
            manager.close()

    def test_unowned_legacy_never_claimed_and_dry_run_never_writes(self):
        destination = self.root / 'new'
        check_owner(destination, self.account)
        self.assertFalse(destination.exists())
        old = self.root / 'old.zip'
        old.write_bytes(sample_zip())
        for create in (False, True):
            with self.assertRaisesRegex(IdentityError, 'DIRECTORY_LEGACY_UNOWNED'):
                check_owner(self.root, self.account, create=create)
        self.assertEqual(list(self.root.iterdir()), [old])

    def test_invalid_or_future_manifest_is_not_overwritten(self):
        owner = self.root / OWNER_NAME
        for data in (b'{', b'[]', b'{"schema_version":"directory-owner-v9"}'):
            owner.write_bytes(data)
            with self.assertRaises(IdentityError):
                check_owner(self.root, self.account, create=True)
            self.assertEqual(owner.read_bytes(), data)

    def test_all_conflicting_download_candidates_preserved(self):
        record = CaseRecord('same-id', 'DVC', account_key=self.account)
        source = source_reference(record, 'zip')
        primary = self.root / 'legacy.zip'
        primary.write_bytes(b'old suspect')
        data = sample_zip()
        first = safe_destination(primary, data, source)
        first.write_bytes(b'other suspect')
        second = safe_destination(primary, data, source)
        self.assertNotEqual(first, second)
        second.write_bytes(data)
        write_evidence(second, validate_tax_zip(data), source)
        self.assertEqual(safe_destination(primary, data, source), second)
        self.assertEqual(primary.read_bytes(), b'old suspect')
        self.assertEqual(first.read_bytes(), b'other suspect')

    def test_catalog_migration_three_kinds_repeat_and_exact_rollback(self):
        for kind, fields in (('DECLARATION', {'ma_ho_so': 'same-id'}),
                             ('GNT', {'ctu_id': 'same-id'}), ('NOTICE', {'message_id': 'same-id'})):
            with self.subTest(kind=kind):
                catalog = self.root / (kind + '.json')
                original = json.dumps([{**fields, 'tep_zip': 'untouched.zip', 'extra': 'preserve'}]).encode()
                catalog.write_bytes(original)
                self.assertEqual(migrate(catalog, kind)['status'], 'PREVIEW')
                self.assertEqual(catalog.read_bytes(), original)
                migrate(catalog, kind, apply=True)
                migrated = catalog.read_bytes()
                row = json.loads(migrated)[0]
                key = RecordKey.parse(row['record_key'])
                self.assertEqual(key.account_key, 'UNKNOWN')
                self.assertEqual(key.source, {'GNT': 'GNT', 'NOTICE': 'TB'}.get(kind, 'UNKNOWN'))
                self.assertEqual(row['extra'], 'preserve')
                migrate(catalog, kind, apply=True)
                self.assertEqual(catalog.read_bytes(), migrated)
                migrate(catalog, kind, rollback=True)
                migrate(catalog, kind, rollback=True)
                self.assertEqual(catalog.read_bytes(), original)
                migrate(catalog, kind, apply=True)
                self.assertEqual(catalog.read_bytes(), migrated)
        self.assertFalse((self.root / OWNER_NAME).exists())

    def test_catalog_or_backup_change_prevents_overwrite(self):
        catalog = self.root / 'legacy.json'
        catalog.write_text('[{"ma_ho_so":"id"}]')
        migrate(catalog, 'DECLARATION', apply=True)
        catalog.write_text('[{"ma_ho_so":"later"}]')
        with self.assertRaisesRegex(IdentityError, 'MIGRATION_CATALOG_CHANGED'):
            migrate(catalog, 'DECLARATION', rollback=True)
        self.assertEqual(json.loads(catalog.read_bytes())[0]['ma_ho_so'], 'later')

    def test_duplicate_catalog_rejected_before_any_write(self):
        catalog = self.root / 'legacy.json'
        catalog.write_text('[{"ma_ho_so":"id"},{"ma_ho_so":"id"}]')
        with self.assertRaisesRegex(IdentityError, 'MIGRATION_DUPLICATE_KEY'):
            migrate(catalog, 'DECLARATION', apply=True)
        self.assertEqual(list(self.root.iterdir()), [catalog])

    def test_other_account_cannot_run_pipeline_in_owned_directory(self):
        check_owner(self.root, self.account, create=True)
        settings = Settings('other-account', 'fake-secret', date(2025, 1, 1), date(2025, 1, 2), self.root)
        for kind in (Pipeline, GntPipeline, TbPipeline):
            http = FakeHttp(lambda *_: self.fail('ownership failure must precede HTTP'))
            factory = Mock()
            pipeline = kind(settings, http, StubCaptcha(), portal_factory=factory)
            with self.assertRaisesRegex(IdentityError, 'DIRECTORY_ACCOUNT_MISMATCH'):
                pipeline.run()
            factory.assert_not_called()
