"""Regression tests for stage lineage, spreadsheet types and batch outcomes."""

from __future__ import annotations

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from gdt_tax.artifact_contracts import lineage, validate_payload
from gdt_tax.errors import GdtError
from gdt_tax.export import build_rows, build_workbook, load_inputs, main, write_csv, write_workbook
from gdt_tax.outcomes import quality_summary
from gdt_tax.parser.cli import write_parsed
from gdt_tax.spreadsheet_values import numeric_cell
from tests.test_export import CLASSIFICATION, MANIFEST, PARSED


def bundle():
    manifest, parsed, classified = copy.deepcopy((MANIFEST, PARSED, CLASSIFICATION))
    for container, declaration, classification in zip(manifest["containers"], parsed["declarations"], classified["classifications"], strict=True):
        member = container["members"][0]
        member.update(member_name=declaration["source_inner_file"], status="ok")
        classification.update(source_zip=declaration["source_zip"], source_inner_file=declaration["source_inner_file"])
    for payload in (parsed, classified):
        payload["lineage"] = lineage(manifest)
    return manifest, parsed, classified


class OfflineContractsTests(unittest.TestCase):
    def test_stale_manifest_is_rejected(self):
        manifest, parsed, classified = bundle()
        manifest["root"] = "different-source"
        with self.assertRaisesRegex(GdtError, "LINEAGE_MISMATCH"):
            build_rows(manifest, parsed, classified, allow_legacy=False)

    def test_legacy_still_checks_hash_and_membership(self):
        manifest, parsed, classified = copy.deepcopy((MANIFEST, PARSED, CLASSIFICATION))
        parsed["declarations"][0]["source_sha256"] = "wrong"
        with self.assertRaisesRegex(GdtError, "HASH_MISMATCH"):
            build_rows(manifest, parsed, classified)
        parsed["declarations"][0]["source_zip"] = "other.zip"
        with self.assertRaisesRegex(GdtError, "MEMBERSHIP_MISMATCH"):
            build_rows(manifest, parsed, classified)

    def test_incomplete_or_duplicate_stage_is_rejected(self):
        for mode in ("missing", "duplicate"):
            manifest, parsed, classified = bundle()
            if mode == "missing":
                parsed["declarations"].pop()
            else:
                parsed["declarations"].append(parsed["declarations"][0])
            with self.assertRaisesRegex(GdtError, "COVERAGE_MISMATCH|DUPLICATE_SOURCE"):
                build_rows(manifest, parsed, classified, allow_legacy=False)

    def test_shared_id_across_sources_preserves_two_classifications(self):
        manifest, parsed, classified = bundle()
        for container, declaration, classification in zip(manifest["containers"], parsed["declarations"], classified["classifications"], strict=True):
            container["members"][0]["artifact_id"] = declaration["artifact_id"] = classification["artifact_id"] = "same"
            container["members"][0]["sha256"] = declaration["source_sha256"] = "same-sha"
        for payload in (parsed, classified):
            payload["lineage"] = lineage(manifest)
        rows = build_rows(manifest, parsed, classified, allow_legacy=False)
        self.assertEqual([r["tax_type"] for r in rows], ["GTGT", "UNKNOWN"])
        self.assertNotEqual(rows[0]["record_id"], rows[1]["record_id"])

    def test_schema_failures_are_controlled(self):
        for payload in ({"declarations": [1]}, {"declarations": [{}], "schema_version": "future"},
                        {"declarations": [{"taxpayer": []}]}, {"declarations": [{"indicators": [1]}]}):
            with self.assertRaises(GdtError):
                validate_payload(payload, "declarations")

    def test_invalid_json_is_not_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "parsed_declarations.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(GdtError, "INPUT_INVALID"):
                load_inputs(root)

    def test_writer_records_manifest_lineage(self):
        manifest, parsed, _ = bundle()
        with tempfile.TemporaryDirectory() as directory:
            target = write_parsed(parsed["declarations"], Path(directory), manifest=manifest)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["lineage"], lineage(manifest))

    def test_saved_workbook_has_literal_strings_numeric_cells_and_audit(self):
        manifest, parsed, classified = bundle()
        first = parsed["declarations"][0]
        first.update(status="error", error="=SECRET()", mapping_version="2", mapping_sha256="hash")
        first["taxpayer"]["tax_code"] = "=1+1"
        first["indicators"] = [
            {"value": "123.45", "value_type": "decimal", "raw_value": "=SOURCE()"},
            {"value": "1234567890123456", "value_type": "integer"},
            {"value": "=1+1", "value_type": "string"},
            {"value": "000123", "value_type": "string"},
        ]
        rows = build_rows(manifest, parsed, classified, allow_legacy=False)
        with tempfile.TemporaryDirectory() as directory:
            target = write_workbook(build_workbook(rows, manifest, parsed, classified), Path(directory) / "report.xlsx")
            workbook = load_workbook(target)
            for sheet in workbook:
                self.assertFalse(any(c.data_type == "f" for row in sheet for c in row))
            indicators = workbook["05_INDICATORS"]
            self.assertEqual(indicators["L2"].value, 123.45)
            self.assertEqual(indicators["L2"].data_type, "n")
            self.assertEqual(indicators["L3"].value, "1234567890123456")
            self.assertIn("PRECISION", indicators["Q3"].value)
            self.assertEqual(indicators["L5"].value, "000123")
            self.assertEqual(workbook["08_PARSE_ERRORS"]["E2"].value, "=SECRET()")
            self.assertEqual(workbook["09_MAPPING_VERSIONS"]["B2"].value, "2")
            workbook.close()

    def test_numeric_boundaries(self):
        for raw in ("NaN", "Infinity", "1e309", "1e-309", "1234567890123456", "invalid"):
            value, warning = numeric_cell(raw, "decimal")
            self.assertEqual(value, raw)
            self.assertIsNotNone(warning)
        self.assertEqual(numeric_cell("-100", "integer"), (-100, None))
        self.assertEqual(numeric_cell(None, "decimal"), (None, None))

    def test_csv_defaults_safe_with_explicit_raw_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for raw in (False, True):
                target = write_csv(root / "report.csv", [{"form_name": "\t=1+1"}], raw=raw)
                with target.open(encoding="utf-8-sig", newline="") as stream:
                    value = next(csv.DictReader(stream))["form_name"]
                self.assertEqual(value, "\t=1+1" if raw else "'\t=1+1")

    def test_export_exit_quality_and_legacy_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in (("manifest_artifact.json", MANIFEST), ("parsed_declarations.json", PARSED), ("phan_loai_artifact.json", CLASSIFICATION)):
                (root / name).write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(main([directory]), 2)
            summary = root / "summary.json"
            self.assertEqual(main([directory, "--allow-legacy-data", "--summary-json", str(summary)]), 1)
            self.assertEqual(json.loads(summary.read_text())["incomplete"], 1)

    def test_partial_extraction_is_not_success(self):
        self.assertEqual(quality_summary("parse", [{"status": "MAPPED", "validation_status": "PARTIAL"}], complete_status="MAPPED")["exit_code"], 1)


if __name__ == "__main__":
    unittest.main()
