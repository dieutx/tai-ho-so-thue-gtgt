"""Fixture changes require deliberate provenance and behavioral contract review."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from gdt_tax.schema_evidence import safe_schema_evidence
from scripts.fixture_manifest import build
from tests.test_table_contracts import read

ROOT = Path(__file__).parent / 'fixtures'


class FixtureProvenanceTests(unittest.TestCase):
    def test_every_fixture_has_a_current_hash_and_provenance(self):
        manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest, build())
        for row in manifest['fixtures']:
            self.assertIn(row['provenance'], {'synthetic', 'inherited_unverified'})
            self.assertTrue(row['sanitization'])
            self.assertTrue(row['adapter_version'])

    def test_search_fixtures_run_real_parsers_with_expected_quality(self):
        rows = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))['fixtures']
        for row in rows:
            if row['operation'] != 'search':
                continue
            with self.subTest(path=row['path']):
                result = read(row['source'], (ROOT / row['path']).read_text(encoding='utf-8'))
                self.assertEqual(result.diagnostics.status, row['expected_outcome'])
                self.assertEqual(len(result.records), row['expected_rows'])
                self.assertEqual(result.diagnostics.skipped_count, 0)

    def test_evidence_sanitizer_does_not_export_fake_identifiers_tokens_or_unknown_markup(self):
        secret = 'synthetic-private-value-123456'
        html = (f'<form id="{secret}" action="https://fixture.test/{secret}">'
                f'<input name="password" value="{secret}"><script>{secret}</script>'
                f'<table><tr><th>Mã hồ sơ</th><th>{secret}</th><td>{secret}</td></tr></table></form>')
        result = safe_schema_evidence(html)
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result['known_fields'], ['ma_ho_so'])
        self.assertEqual(result['tag_counts']['form'], 1)
        changed = html.replace(secret, 'different-private-value')
        self.assertEqual(safe_schema_evidence(changed), result)

    def test_evidence_sanitizer_is_bounded_and_tracks_structural_drift(self):
        self.assertEqual(safe_schema_evidence('x' * (2 * 1024 * 1024 + 1)), {'code': 'EVIDENCE_LIMIT'})
        self.assertNotEqual(safe_schema_evidence('<table><tr><td>x</td></tr></table>')['fingerprint'],
                            safe_schema_evidence('<table><tr><td>x</td><td>y</td></tr></table>')['fingerprint'])
