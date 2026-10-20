"""Synthetic CORE-07/10/26 fixtures; no portal captures or taxpayer data.

RETURN_XML/NOTICE_XML are hand-authored in test_inventory.py. Mutations below
exercise namespace, scope and cache contracts; they are not tax schema evidence.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from gdt_tax.classify import classify_artifact, classify_manifest
from gdt_tax.export import build_rows, build_workbook
from gdt_tax.inventory import load_cache, profile_xml, scan_directory, write_manifest
from tests.test_classify import registry
from tests.test_export import CLASSIFICATION, MANIFEST, PARSED
from tests.test_inventory import NOTICE_XML, RETURN_XML


class InventoryContracts(unittest.TestCase):
    def test_cache_root_profile_policy_and_schema_are_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.mkdir()
            b.mkdir()
            (a / "x.xml").write_bytes(RETURN_XML)
            (b / "x.xml").write_bytes(RETURN_XML.replace(b"842", b"999"))
            stat = (a / "x.xml").stat()
            os.utime(b / "x.xml", ns=(stat.st_atime_ns, stat.st_mtime_ns))
            path = write_manifest(scan_directory(a), a)
            cache = load_cache(path)
            actual = scan_directory(b, cache=cache)
            self.assertEqual(actual.containers[0].members[0].xml.possible_form_code, "999")
            payload = json.loads(path.read_text(encoding="utf-8"))
            for key in ("profile_version", "schema_version", "cache_policy"):
                with self.subTest(key=key):
                    bad = {**payload, key: "obsolete"}
                    path.write_text(json.dumps(bad), encoding="utf-8")
                    self.assertEqual(load_cache(path), {})

    def test_cache_is_copied_and_force_rehash_detects_same_stat_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "x.xml"
            source.write_bytes(RETURN_XML)
            cache = load_cache(write_manifest(scan_directory(root), root))
            before = asdict(cache["x.xml"])
            second = scan_directory(root, cache=cache)
            second.containers[0].members[0].xml.possible_form_code = "changed"
            self.assertEqual(asdict(cache["x.xml"]), before)
            stat = source.stat()
            source.write_bytes(RETURN_XML.replace(b"842", b"999"))
            os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            # Stat cache deliberately cannot detect equal-size/equal-mtime changes.
            self.assertEqual(scan_directory(root, cache=cache).containers[0].sha256, before["sha256"])
            forced = scan_directory(root, cache=cache, force=True)
            self.assertNotEqual(forced.containers[0].sha256, before["sha256"])

    def test_plain_dictionary_cache_has_no_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "x.xml").write_bytes(RETURN_XML)
            cache = {c.rel_path: c for c in scan_directory(root).containers}
            with patch("gdt_tax.inventory._scan_one", wraps=__import__(
                    "gdt_tax.inventory", fromlist=["_scan_one"])._scan_one) as scan:
                scan_directory(root, cache=cache)
                scan.assert_called_once()

    def test_oversized_raw_source_rejected_before_hash_or_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "x.xml").write_bytes(RETURN_XML)
            with patch("gdt_tax.inventory.MAX_XML_BYTES", 20), patch(
                    "gdt_tax.inventory.sha256_file", side_effect=AssertionError("unbounded hash")):
                result = scan_directory(root)
            self.assertEqual(result.containers[0].error, "SOURCE_TOO_LARGE")

    def test_io_failures_preserve_other_files(self):
        import gdt_tax.inventory as inventory
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.xml", "b.xml"):
                (root / name).write_bytes(RETURN_XML)
            real = inventory.sha256_file
            def hashing(path):
                if path.name == "a.xml":
                    raise OSError("synthetic read failure")
                return real(path)
            with patch.object(inventory, "sha256_file", side_effect=hashing):
                result = scan_directory(root)
            self.assertEqual([c.status for c in result.containers], ["error", "ok"])
            self.assertEqual(len(result.errors), 1)
            # Stat failures after discovery must also become per-file diagnostics.
            stat = Path.stat
            count = 0
            def failing_stat(path, *args, **kwargs):
                nonlocal count
                if path.name == "a.xml":
                    count += 1
                    if count > 1:
                        raise OSError("synthetic stat failure")
                return stat(path, *args, **kwargs)
            with patch.object(Path, "stat", failing_stat):
                self.assertTrue(scan_directory(root).errors)

    def test_symlink_rejected_without_reading_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "x.xml").write_bytes(RETURN_XML)
            real = Path.is_symlink
            with patch.object(Path, "is_symlink", lambda p: p.name == "x.xml" or real(p)):
                result = scan_directory(root)
            self.assertIn("SYMLINK", result.containers[0].error)

    def test_namespace_and_appendix_metadata_cannot_shadow_primary(self):
        injected = RETURN_XML.replace(b"<TTinChung>", b'<PLuc><maTKhai>999</maTKhai></PLuc>'
                                     b'<evil:maTKhai xmlns:evil="urn:evil">888</evil:maTKhai><TTinChung>')
        profile = profile_xml(injected)
        self.assertEqual(profile.possible_form_code, "842")
        self.assertIn("PLuc", profile.structural_markers)
        self.assertNotEqual(profile.structure_skeleton, profile_xml(RETURN_XML).structure_skeleton)
        wrapped = profile_xml(b'<Envelope xmlns="urn:wrapper">' + RETURN_XML.split(b"?>", 1)[1] + b"</Envelope>")
        self.assertEqual(wrapped.possible_form_code, "842")
        self.assertEqual(wrapped.namespace, profile.namespace)
        self.assertEqual(wrapped.document_root, "HSoThueDTu")
        self.assertIn("http://kekhaithue.gdt.gov.vn/TKhaiThue", wrapped.namespaces)

    def test_document_roles_and_coverage_are_structural(self):
        cases = [(RETURN_XML, "DECLARATION", "OK"), (NOTICE_XML, "NOTICE", "UNKNOWN"),
                 (b"<PLuc><BangKe/></PLuc>", "APPENDIX", "UNKNOWN"),
                 (b"<mystery/>", "UNKNOWN", "UNKNOWN"),
                 (b"<TBao><HSoKhaiThue/></TBao>", "UNKNOWN", "CONFLICT")]
        for payload, role, status in cases:
            with self.subTest(role=role, status=status):
                result = classify_artifact(artifact_id="a", source_zip=None,
                    source_inner_file="x.xml", xml_profile=asdict(profile_xml(payload)), registry=registry())
                self.assertEqual((result.document_role, result.status), (role, status))
                self.assertEqual(result.acceptance_status, "UNKNOWN")
        result = classify_artifact(artifact_id="a", source_zip=None, source_inner_file="x.xml",
                                   xml_profile=asdict(profile_xml(RETURN_XML)), registry=registry())
        self.assertEqual(result.mapping_coverage["present_count"], 2)
        self.assertEqual(result.mapping_coverage["missing_codes"], ["ct43"])

    def test_acceptance_metadata_is_unverified_even_when_it_says_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "x.xml").write_bytes(RETURN_XML)
            manifest = scan_directory(root).to_dict()
            manifest["containers"][0]["case"] = {"trang_thai": "chấp nhận"}
            row = classify_manifest(manifest, registry=registry())[0]
            self.assertEqual(row["file_integrity"], "OK")
            self.assertEqual(row["acceptance_status"], "UNKNOWN")
            self.assertEqual(row["acceptance_raw"], "chấp nhận")
            self.assertIn("unverified", row["acceptance_source"])
            self.assertIsNone(row["acceptance_verified_at"])

    def test_export_keeps_quality_integrity_acceptance_and_coverage_separate(self):
        from copy import deepcopy
        classification = deepcopy(CLASSIFICATION)
        classification["classifications"][0].update({
            "file_integrity": "OK", "acceptance_status": "UNKNOWN",
            "acceptance_raw": "reported accepted", "acceptance_source": "unverified metadata",
            "mapping_coverage": {"status": "MAPPED", "missing_count": 1, "missing_codes": ["ct43"]}})
        rows = build_rows(MANIFEST, PARSED, classification)
        self.assertEqual((rows[0]["status"], rows[0]["file_integrity"], rows[0]["acceptance_status"]),
                         ("MAPPED", "OK", "UNKNOWN"))
        workbook = build_workbook(rows, MANIFEST, PARSED, classification)
        headers = [cell.value for cell in workbook["01_RETURN_INDEX"][1]]
        self.assertIn("Toàn vẹn tệp", headers)
        self.assertIn("Trạng thái tiếp nhận đã kiểm chứng", headers)
        coverage = list(workbook["12_MAPPING_COVERAGE"].values)
        self.assertIn("ct43", coverage[1])
        self.assertEqual(len(rows), len(PARSED["declarations"]))
        workbook.close()
