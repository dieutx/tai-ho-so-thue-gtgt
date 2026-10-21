"""Offline build contracts with fake artifacts; never invokes a build or release."""
from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from scripts.build_provenance import build_receipt
from scripts.dependency_inventory import inventory, verify
from scripts.run_test_gate import gate_payload
from scripts.write_release_metadata import write_metadata
from tests.support import temporary_directory


class BuildProvenanceTests(unittest.TestCase):
    def test_inventory_rejects_version_metadata_and_transitive_changes(self):
        current = inventory()
        verify(current, current)
        for field in ('version', 'metadata_sha256', 'wheel_sha256'):
            altered = deepcopy(current)
            altered['packages'][0][field] = 'changed'
            with self.assertRaisesRegex(ValueError, 'INVENTORY_MISMATCH'):
                verify(current, altered)

    def test_desktop_gate_cannot_succeed_by_skipping_qt_or_default_ocr(self):
        test = SimpleNamespace(id=lambda: 'tests.test_desktop.QtTest')
        result = SimpleNamespace(skipped=[(test, 'Optional Qt')], testsRun=1, failures=[], errors=[], wasSuccessful=lambda: True)
        self.assertTrue(gate_payload(result, 'minimal', 'a' * 40)['pass'])
        self.assertFalse(gate_payload(result, 'desktop', 'a' * 40)['pass'])
        result.skipped = []
        self.assertTrue(gate_payload(result, 'desktop', 'a' * 40)['pass'])

    def test_receipt_binds_source_frozen_gates_and_both_asset_hashes(self):
        with temporary_directory() as directory:
            root = Path(directory)
            for name in ('packaging', 'desktop/resources', '.cache/ci', '.cache/smoke-test', 'dist'):
                (root / name).mkdir(parents=True)
            for name in ('desktop', 'build-tools'):
                (root / f'packaging/{name}-windows-py311.inventory.json').write_text('{}')
            write_metadata(root, 'a' * 40)
            # PyInstaller loads this as an expression; indented trailing lines
            # raise IndentationError even when the metadata JSON is valid.
            compile((root / 'packaging/version.txt').read_text(encoding='utf-8'), 'version.txt', 'eval')
            (root / '.cache/ci/desktop.json').write_text(json.dumps({'pass': True, 'source_sha': 'a' * 40}))
            (root / '.cache/bundle-audit.json').write_text('{"pass":true}')
            (root / '.cache/last-smoke-path.txt').write_text(str(root / '.cache/smoke-test'))
            for index in (1, 2):
                (root / f'.cache/smoke-test/report-{index}.json').write_text(json.dumps({'pass': True, 'frozen': True, 'source_sha': 'a' * 40}))
            (root / 'dist/TaiHoSoThue-Windows.exe').write_bytes(b'synthetic-artifact-not-executable')
            receipt = build_receipt(root)
            self.assertEqual(receipt['core_version'], '1.0.0')
            self.assertEqual(receipt['version'], '2.0.2')
            self.assertEqual(set(receipt['assets']), {'TaiHoSoThue-Windows.exe', 'SHA256SUMS.txt'})
            self.assertEqual(receipt['source_sha'], 'a' * 40)
            (root / '.cache/ci/desktop.json').write_text(json.dumps({'pass': True, 'source_sha': 'b' * 40}))
            with self.assertRaisesRegex(ValueError, 'GATE_FAILED'):
                build_receipt(root)

    def test_invalid_source_sha_rejected_before_metadata_write(self):
        with temporary_directory() as directory:
            with self.assertRaisesRegex(ValueError, 'SOURCE_SHA_INVALID'):
                write_metadata(Path(directory), 'not-a-revision')
