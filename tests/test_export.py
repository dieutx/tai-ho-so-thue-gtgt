"""Test xuất Excel/CSV và truy vấn (stage 08)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from gdt_tax.export import (
    build_rows,
    build_workbook,
    filter_rows,
    record_id,
    write_csv,
    write_workbook,
)

PARSED = {
    "schema_version": "parsed-declaration-v1",
    "parser_version": "declaration-parser-v1",
    "declarations": [
        {
            "artifact_id": "a1",
            "source_zip": "z1.zip",
            "source_inner_file": "x.xml",
            "source_sha256": "sha-1",
            "form_code": "842",
            "form_name": "01/GTGT",
            "form_version": "2.8.3",
            "tax_type_hint": "GTGT",
            "filing_type": "C",
            "supplement_number": "0",
            "status": "MAPPED",
            "mapping_id": "GTGT_842",
            "taxpayer": {"tax_code": "0000000000", "name": "CÔNG TY A"},
            "period": {"raw": "06/2025", "period_type": "M"},
            "indicators": [
                {"code": "ct40", "canonical_name": "vat_payable", "value": "-100",
                 "raw_value": "-100", "status": "MAPPED", "xpath": ".//CTieuTKhaiChinh/ct40"},
                {"code": "ct22", "canonical_name": "total_revenue", "value": "0",
                 "raw_value": "0", "status": "MAPPED", "xpath": ".//CTieuTKhaiChinh/ct22"},
            ],
        },
        {
            "artifact_id": "a2",
            "source_zip": "z2.zip",
            "source_inner_file": "y.xml",
            "source_sha256": "sha-2",
            "form_code": "999",
            "form_name": "=FORMULA()",
            "form_version": "1.0",
            "status": "NEED_MAPPING",
            "taxpayer": {"tax_code": "0000000001", "name": "CÔNG TY B"},
            "period": {"raw": "07/2025", "period_type": "M"},
            "indicators": [],
        },
    ],
}

MANIFEST = {
    "containers": [
        {"rel_path": "z1.zip", "members": [{"artifact_id": "a1", "format": "xml", "sha256": "sha-1"}]},
        {"rel_path": "z2.zip", "members": [{"artifact_id": "a2", "format": "xml", "sha256": "sha-2"}]},
    ]
}

CLASSIFICATION = {
    "count": 2,
    "classifications": [
        {"artifact_id": "a1", "tax_group": "GTGT", "document_role": "DECLARATION", "status": "OK"},
        {"artifact_id": "a2", "tax_group": "UNKNOWN", "document_role": "DECLARATION", "status": "UNKNOWN"},
    ],
}


class ExportTests(unittest.TestCase):
    def test_record_id_stable_and_not_sequential(self) -> None:
        first = record_id("sha-1", "a1")
        self.assertEqual(first, record_id("sha-1", "a1"))
        self.assertNotEqual(first, "1")
        self.assertNotEqual(first, record_id("sha-2", "a1"))

    def test_build_rows_joins_sources(self) -> None:
        rows = build_rows(MANIFEST, PARSED, CLASSIFICATION)
        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first["tax_type"], "GTGT")
        self.assertEqual(first["taxpayer_tax_code"], "0000000000")
        self.assertEqual(first["source_sha256"], "sha-1")
        self.assertEqual(len(first["indicators"]), 2)

    def test_filter_preserves_history(self) -> None:
        rows = build_rows(MANIFEST, PARSED, CLASSIFICATION)
        gtgt = filter_rows(rows, tax_group="GTGT")
        self.assertEqual(len(gtgt), 1)
        # Lọc không làm mất dòng khác trong nguồn gốc.
        self.assertEqual(len(rows), 2)

    def test_workbook_has_expected_sheets(self) -> None:
        rows = build_rows(MANIFEST, PARSED, CLASSIFICATION)
        workbook = build_workbook(rows, MANIFEST, PARSED, CLASSIFICATION)
        names = workbook.sheetnames
        for expected in ("00_README", "01_RETURN_INDEX", "02_GTGT", "05_INDICATORS",
                         "07_UNMAPPED_FORMS", "10_AUDIT_LOG"):
            self.assertIn(expected, names)
        workbook.close()

    def test_negative_money_kept_and_formula_escaped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = build_rows(MANIFEST, PARSED, CLASSIFICATION)
            workbook = build_workbook(rows, MANIFEST, PARSED, CLASSIFICATION)
            path = write_workbook(workbook, Path(tmp) / "out.xlsx")
            loaded = load_workbook(path, read_only=True)
            index = loaded["01_RETURN_INDEX"]
            values = list(index.iter_rows(values_only=True))
            headers = values[0]
            name_col = headers.index("Tên mẫu")
            formulas = [row[name_col] for row in values[1:] if row[name_col] and str(row[name_col]).startswith(("=", "'"))]
            self.assertTrue(formulas)  # text bắt đầu bằng '=' phải được escape
            indicators = loaded["05_INDICATORS"]
            ivalues = list(indicators.iter_rows(values_only=True))
            vcol = ivalues[0].index("value")
            self.assertIn("-100", [str(r[vcol]) for r in ivalues[1:]])
            loaded.close()

    def test_csv_written_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = build_rows(MANIFEST, PARSED, CLASSIFICATION)
            path = write_csv(Path(tmp) / "out.csv", rows)
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    unittest.main()