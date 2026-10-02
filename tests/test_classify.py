"""Test phân loại artifact theo nội dung (stage 03)."""

from __future__ import annotations

import unittest

from gdt_tax.classify import classify_artifact, classify_manifest
from gdt_tax.parser.registry import FieldMapping, FormMapping, MappingRegistry


def registry() -> MappingRegistry:
    reg = MappingRegistry()
    reg.add(
        FormMapping(
            mapping_id="GTGT_842",
            mapping_version="1",
            form_code="842",
            form_version=None,
            tax_type="GTGT",
            fields={"vat": FieldMapping(canonical_name="vat", indicator_code="ct43")},
        )
    )
    return reg


class ClassifyTests(unittest.TestCase):
    def test_mapping_wins_over_name(self) -> None:
        cls = classify_artifact(
            artifact_id="a1",
            source_zip="z.zip",
            source_inner_file="x.xml",
            xml_profile={"root_element": "HSoThueDTu", "possible_form_code": "842",
                         "possible_form_version": "2.8.3", "possible_form_name": "GTGT"},
            registry=registry(),
        )
        self.assertEqual(cls.tax_group, "GTGT")
        self.assertEqual(cls.document_role, "DECLARATION")
        self.assertEqual(cls.status, "OK")
        self.assertIn("mapping", " ".join(cls.evidence))

    def test_unknown_without_mapping_and_name(self) -> None:
        cls = classify_artifact(
            artifact_id="a2",
            source_zip=None,
            source_inner_file="y.xml",
            xml_profile={"root_element": "HSoThueDTu", "possible_form_code": "999",
                         "possible_form_version": "1.0", "possible_form_name": None},
            registry=registry(),
        )
        self.assertEqual(cls.tax_group, "UNKNOWN")
        self.assertEqual(cls.status, "UNKNOWN")

    def test_notice_role(self) -> None:
        cls = classify_artifact(
            artifact_id="a3",
            source_zip="z.zip",
            source_inner_file="tb.xml",
            xml_profile={"root_element": "TBao", "possible_form_code": "04/SS-HDDT"},
            registry=registry(),
        )
        self.assertEqual(cls.document_role, "NOTICE")

    def test_name_guess_when_no_mapping(self) -> None:
        cls = classify_artifact(
            artifact_id="a4",
            source_zip="z.zip",
            source_inner_file="t.xml",
            xml_profile={"root_element": "HSoThueDTu", "possible_form_code": "864",
                         "possible_form_name": "Tờ khai thuế thu nhập cá nhân"},
            registry=registry(),
        )
        self.assertEqual(cls.tax_group, "TNCN")
        self.assertIn("tên mẫu", cls.reason or "")

    def test_classify_manifest_skips_pdf(self) -> None:
        manifest = {
            "containers": [
                {
                    "rel_path": "z.zip",
                    "members": [
                        {"artifact_id": "a1", "member_name": "x.xml", "format": "xml",
                         "xml": {"root_element": "HSoThueDTu", "possible_form_code": "842"}},
                        {"artifact_id": "a2", "member_name": "p.pdf", "format": "pdf"},
                    ],
                }
            ]
        }
        results = classify_manifest(manifest, registry=registry())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["tax_group"], "GTGT")


if __name__ == "__main__":
    unittest.main()