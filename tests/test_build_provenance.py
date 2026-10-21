"""Offline build contracts with fake artifacts; never invokes a build or release."""
from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from desktop import __version__ as desktop_version
from scripts.build_provenance import build_receipt
from scripts.dependency_inventory import inventory, verify
from scripts.run_test_gate import gate_payload
from scripts.write_release_metadata import source_version, write_metadata
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
            for name in ('report-1.json', 'report-2.json', 'source-report.json'):
                (root / '.cache/smoke-test' / name).write_text(json.dumps({'pass': True,
                    'frozen': name != 'source-report.json', 'source_sha': 'a' * 40,
                    'version': desktop_version, 'release_version': desktop_version, 'core_version': '1.0.0'}))
            (root / 'dist/TaiHoSoThue-Windows.exe').write_bytes(b'synthetic-artifact-not-executable')
            receipt = build_receipt(root)
            self.assertEqual(receipt['core_version'], '1.0.0')
            self.assertEqual(receipt['version'], desktop_version)
            self.assertEqual(set(receipt['assets']), {'TaiHoSoThue-Windows.exe', 'SHA256SUMS.txt'})
            self.assertEqual(receipt['source_sha'], 'a' * 40)
            frozen_path = root / '.cache/smoke-test/report-1.json'
            frozen = json.loads(frozen_path.read_text())
            frozen_path.write_text(json.dumps(frozen | {'version': '0.0.0'}))
            with self.assertRaisesRegex(ValueError, 'FROZEN_GATE_FAILED'):
                build_receipt(root)
            frozen_path.write_text(json.dumps(frozen))
            source_path = root / '.cache/smoke-test/source-report.json'
            source = json.loads(source_path.read_text())
            source_path.write_text(json.dumps(source | {'version': '0.0.0'}))
            with self.assertRaisesRegex(ValueError, 'SOURCE_SMOKE_GATE_FAILED'):
                build_receipt(root)
            source_path.write_text(json.dumps(source))
            (root / '.cache/ci/desktop.json').write_text(json.dumps({'pass': True, 'source_sha': 'b' * 40}))
            with self.assertRaisesRegex(ValueError, 'GATE_FAILED'):
                build_receipt(root)

    def test_metadata_versions_come_from_source_files_not_installed_packages(self):
        with temporary_directory() as directory:
            root = Path(directory)
            source = root / 'source'
            for package, version in (('desktop', '7.8.9'), ('gdt_tax', '4.5.6')):
                (source / package).mkdir(parents=True)
                (source / package / '__init__.py').write_text(f'__version__ = "{version}"\n')
            output = root / 'output'
            for name in ('packaging', 'desktop/resources'):
                (output / name).mkdir(parents=True)
            for name in ('desktop', 'build-tools'):
                (output / f'packaging/{name}-windows-py311.inventory.json').write_text('{}')
            with patch.dict(sys.modules, {'desktop': SimpleNamespace(__version__='0.0.0'),
                                          'gdt_tax': SimpleNamespace(__version__='0.0.0')}):
                write_metadata(output, 'a' * 40, source_root=source)
            info = json.loads((output / 'desktop/resources/release.json').read_text())
            self.assertEqual((info['version'], info['core_version']), ('7.8.9', '4.5.6'))
            self.assertIn('filevers=(7, 8, 9, 0)', (output / 'packaging/version.txt').read_text())
            (source / 'desktop/__init__.py').write_text('__version__ = get_version()')
            with self.assertRaisesRegex(ValueError, 'SOURCE_VERSION_INVALID'):
                source_version(source, 'desktop')

    def test_invalid_source_sha_rejected_before_metadata_write(self):
        with temporary_directory() as directory:
            with self.assertRaisesRegex(ValueError, 'SOURCE_SHA_INVALID'):
                write_metadata(Path(directory), 'not-a-revision')
