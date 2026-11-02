"""LOCAL FIRST: khôi phục danh mục trên máy, chống trùng và lọc theo ngày."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from desktop.library import (
    check_files,
    date_in_range,
    dedupe,
    load_library,
    merge_rows,
    parse_date,
    read_catalog,
)
from desktop.services import JobResult, RunConfig
from desktop.state import job_output
from gdt_tax.identity import account_fingerprint
from gdt_tax.integrity import source_reference, validate_tax_zip, write_evidence
from gdt_tax.models import CaseRecord
from gdt_tax.ownership import check_owner
from gdt_tax.run_hooks import RunHooks
from tests.support import sample_zip


def tax_row(case_id: str, day: str = "05/10/2026", name: str = "") -> dict:
    return {"nguon": "DVC", "ma_ho_so": case_id, "to_khai": "01/GTGT", "ky_tinh_thue": "10/2026",
            "ngay_nop": day, "tep_zip": name}


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_catalog(self, folder: Path, rows: list[dict], name: str = "danh_sach_ho_so.json") -> None:
        account = account_fingerprint('0111214430-QL' if folder.parent.name.startswith('0111214430') else '0101234567-ql')
        check_owner(folder, account, create=True)
        rows = [dict(row, account_key=account) for row in rows]
        (folder / name).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def test_missing_catalog_is_empty_not_an_error(self):
        self.assertEqual(read_catalog("tax", self.base / "khong-co"), [])

    def test_corrupt_catalog_reports_readable_error(self):
        folder = self.base / "hong"
        folder.mkdir()
        (folder / "danh_sach_ho_so.json").write_text("{khong-phai-json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "danh_sach_ho_so.json"):
            read_catalog("tax", folder)

    def test_dedupe_keeps_one_row_per_submission_key(self):
        rows = [tax_row("A"), tax_row("A", name="a.zip"), tax_row("B")]
        merged = dedupe("tax", rows)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["tep_zip"], "a.zip")

    def test_merge_keeps_downloaded_file_when_online_row_has_none(self):
        local = [{"ma_ho_so": "A", "ngay_nop": "05/10/2026", "tep_zip": "A.zip",
                  "_file_status": "downloaded", "_file_path": "/x/A.zip"}]
        online = [{"ma_ho_so": "A", "ngay_nop": "05/10/2026", "tep_zip": "", "trang_thai": "Đã chấp nhận"}]
        merged = merge_rows("tax", local, online)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["trang_thai"], "Đã chấp nhận")
        self.assertEqual(merged[0]["_file_status"], "downloaded")
        self.assertEqual(merged[0]["_file_path"], "/x/A.zip")

    def test_merge_counts_union_without_duplicates(self):
        local = [{"ma_ho_so": str(index), "ngay_nop": "05/10/2026"} for index in range(100)]
        online = [{"ma_ho_so": str(index), "ngay_nop": "05/10/2026"} for index in range(105)]
        self.assertEqual(len(merge_rows("tax", local, online)), 105)
        self.assertEqual(len(merge_rows("tax", local, local)), 100)

    def test_overlapping_ranges_do_not_duplicate(self):
        first = [{"ma_ho_so": "A", "ngay_nop": "01/10/2026"}, {"ma_ho_so": "B", "ngay_nop": "15/10/2026"}]
        second = [{"ma_ho_so": "B", "ngay_nop": "15/10/2026"}, {"ma_ho_so": "C", "ngay_nop": "31/10/2026"}]
        self.assertEqual(len(merge_rows("tax", first, second)), 3)

    def test_check_files_marks_present_and_missing_files(self):
        folder = self.base / "so"
        folder.mkdir()
        (folder / "co.zip").write_bytes(b"PK\x03\x04du-lieu")
        rows = check_files("tax", [dict(tax_row("A", name="co.zip"), _file_status='downloaded',
                                       _file_size=11, _file_hash=hashlib.sha256(b"PK\x03\x04du-lieu").hexdigest()),
                                   tax_row("B", name="mat.zip")], folder)
        self.assertEqual(rows[0]["_file_status"], "downloaded")
        self.assertTrue(rows[0]["_file_path"].endswith("co.zip"))
        self.assertEqual(rows[1]["_file_status"], "not_downloaded")
        self.assertIn("xóa", rows[1]["_file_reason"])

    def test_empty_file_is_not_reused(self):
        folder = self.base / "so2"
        folder.mkdir()
        (folder / "rong.zip").write_bytes(b"")
        rows = check_files("tax", [tax_row("A", name="rong.zip")], folder)
        self.assertEqual(rows[0]["_file_status"], "not_downloaded")

    def test_date_range_includes_both_bounds_and_keeps_unknown_dates(self):
        start, end = date(2026, 10, 1), date(2026, 10, 31)
        self.assertTrue(date_in_range("tax", {"ngay_nop": "01/10/2026"}, start, end))
        self.assertTrue(date_in_range("tax", {"ngay_nop": "31/10/2026 09:30:00"}, start, end))
        self.assertFalse(date_in_range("tax", {"ngay_nop": "30/09/2026"}, start, end))
        self.assertFalse(date_in_range("tax", {"ngay_nop": "01/11/2026"}, start, end))
        self.assertFalse(date_in_range("tax", {"ngay_nop": ""}, start, end))

    def test_parse_date_accepts_time_and_iso(self):
        self.assertEqual(parse_date("05/10/2026 08:00:00"), date(2026, 10, 5))
        self.assertEqual(parse_date("2026-10-05T08:00:00"), date(2026, 10, 5))
        self.assertEqual(parse_date("05/10/2026"), date(2026, 10, 5))
        self.assertIsNone(parse_date("không rõ"))

    def test_load_library_restores_only_the_given_account_folder(self):
        config_a = RunConfig("library", self.base, username="0101234567-ql", from_date='01/10/2026', to_date='31/10/2026')
        folder_a = job_output(self.base, "0101234567-ql", "tax")
        self.write_catalog(folder_a, [tax_row("A", name="A.zip")])
        (folder_a / "A.zip").write_bytes(sample_zip())
        write_evidence(folder_a / 'A.zip', validate_tax_zip(sample_zip()),
                       source_reference(CaseRecord('A', 'DVC', account_key=account_fingerprint(config_a.username)), 'zip'))
        folder_b = job_output(self.base, "0111214430-QL", "tax")
        self.write_catalog(folder_b, [tax_row("Z", name="Z.zip")])

        result = load_library(config_a, RunHooks())
        self.assertEqual(result.state, "LOADED")
        self.assertEqual(set(result.children), {"tax", "gnt", "notice"})
        rows = result.children["tax"].rows
        self.assertEqual([row["ma_ho_so"] for row in rows], ["A"])
        self.assertEqual(rows[0]["_file_status"], "downloaded")
        self.assertEqual(result.children["gnt"].rows, [])

    def test_load_library_is_idempotent(self):
        config = RunConfig("library", self.base, username="0101234567-ql", from_date='01/10/2026', to_date='31/10/2026')
        folder = job_output(self.base, "0101234567-ql", "tax")
        self.write_catalog(folder, [tax_row("A"), tax_row("A"), tax_row("B")])
        first = load_library(config, RunHooks())
        second = load_library(config, RunHooks())
        self.assertEqual(len(first.children["tax"].rows), 2)
        self.assertEqual(len(second.children["tax"].rows), 2)

    def test_load_library_surfaces_corrupt_catalog_as_error_state(self):
        config = RunConfig("library", self.base, username="0101234567-ql")
        folder = job_output(self.base, "0101234567-ql", "tax")
        check_owner(folder, account_fingerprint('0101234567-ql'), create=True)
        (folder / "danh_sach_ho_so.json").write_text("{hong", encoding="utf-8")
        result = load_library(config, RunHooks())
        self.assertEqual(result.children["tax"].state, "ERROR")
        self.assertIn("danh_sach_ho_so.json", result.children["tax"].message)


class MergeContractTests(unittest.TestCase):
    def test_rows_from_two_tabs_are_never_mixed(self):
        tax = [{"ma_ho_so": "A", "ngay_nop": "05/10/2026"}]
        notice = [{"message_id": "A", "ngay_gui": "05/10/2026"}]
        self.assertEqual(len(merge_rows("tax", tax, [])), 1)
        self.assertEqual(len(merge_rows("notice", notice, [])), 1)

    def test_job_result_children_are_independent(self):
        result = JobResult("LOADED", "x", Path("."), children={})
        result.children["tax"] = JobResult("LOADED", "tax", Path("."), rows=[{}])
        result.children["gnt"] = JobResult("LOADED", "gnt", Path("."), rows=[])
        self.assertEqual(len(result.children["tax"].rows), 1)
        self.assertEqual(result.children["gnt"].rows, [])


if __name__ == "__main__":
    unittest.main()
