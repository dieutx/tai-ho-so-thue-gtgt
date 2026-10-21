"""Desktop upgrades select a fresh namespace without adopting legacy data."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from desktop.state import job_output
from gdt_tax.identity import IdentityError, account_fingerprint
from gdt_tax.ownership import OWNER_NAME, check_owner
from tests.support import cleanup_temporary_directory


class DesktopOutputUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.username = 'synthetic-upgrade-QL'
        self.key = account_fingerprint(self.username)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def test_legacy_files_are_preserved_and_lookup_creates_no_directories(self):
        for mode in ('tax', 'gnt', 'notice'):
            with self.subTest(mode=mode):
                old = job_output(self.base, self.username, mode)
                old.mkdir(parents=True)
                original = b'synthetic legacy data'
                (old / 'legacy.xml').write_bytes(original)
                fresh = job_output(self.base, self.username, mode)
                self.assertNotEqual(fresh, old)
                self.assertFalse(fresh.exists())
                self.assertFalse((old / OWNER_NAME).exists())
                self.assertEqual((old / 'legacy.xml').read_bytes(), original)
                check_owner(fresh, self.key, create=True)
                self.assertEqual(job_output(self.base, self.username, mode), fresh)
                (old / 'legacy.xml').unlink()
                self.assertEqual(job_output(self.base, self.username, mode), fresh)

    def test_existing_owned_output_remains_reusable(self):
        old = job_output(self.base, self.username, 'tax')
        check_owner(old, self.key, create=True)
        self.assertEqual(job_output(self.base, self.username, 'tax'), old)

    def test_mismatch_or_broken_owner_does_not_silently_redirect(self):
        old = job_output(self.base, self.username, 'tax')
        check_owner(old, account_fingerprint('other-account'), create=True)
        with self.assertRaisesRegex(IdentityError, 'DIRECTORY_ACCOUNT_MISMATCH'):
            job_output(self.base, self.username, 'tax')
        (old / OWNER_NAME).write_bytes(b'{')
        with self.assertRaisesRegex(IdentityError, 'DIRECTORY_OWNER_INVALID'):
            job_output(self.base, self.username, 'tax')

    def test_new_namespace_with_unknown_data_is_not_adopted(self):
        old = job_output(self.base, self.username, 'tax')
        old.mkdir(parents=True)
        (old / 'legacy.xml').write_bytes(b'old')
        fresh = job_output(self.base, self.username, 'tax')
        fresh.mkdir(parents=True)
        (fresh / 'unknown.xml').write_bytes(b'unknown')
        with self.assertRaisesRegex(IdentityError, 'DIRECTORY_LEGACY_UNOWNED'):
            job_output(self.base, self.username, 'tax')

    def test_offline_output_does_not_require_an_account(self):
        self.assertEqual(job_output(self.base, '', 'offline'), self.base / 'phan-tich')
