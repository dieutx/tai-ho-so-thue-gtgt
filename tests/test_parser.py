"""Test cho khung parser tờ khai (stage 04).

Fixture tổng hợp trong bộ nhớ; không có hồ sơ thật, không gọi mạng. Kiểm chứng:
trích metadata chung, chỉ tiêu + provenance XPath, phân biệt NULL/0, không lấy
chỉ tiêu chi tiết, mapping theo registry, unknown form, XML lỗi.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from gdt_tax.parser import (
    MappingRegistry,
    extract_declaration,
    load_registry,
    normalize_number,
)
from gdt_tax.parser.cli import parse_manifest
from gdt_tax.parser.registry import FieldMapping, FormMapping
from tests.support import FIXTURES

RETURN_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HSoThueDTu xmlns="http://kekhaithue.gdt.gov.vn/TKhaiThue">
  <HSoKhaiThue id="ID_1">
    <TTinChung><TTinTKhaiThue><TKhaiThue>
      <maTKhai>842</maTKhai>
      <tenTKhai>TO KHAI THUE GIA TRI GIA TANG (Mau so 01/GTGT)</tenTKhai>
      <pbanTKhaiXML>2.8.3</pbanTKhaiXML>
      <loaiTKhai>B</loaiTKhai>
      <soLan>1</soLan>
      <KyKKhaiThue>
        <kieuKy>M</kieuKy><kyKKhai>06/2025</kyKKhai>
        <kyKKhaiTuNgay>01/06/2025</kyKKhaiTuNgay>
        <kyKKhaiDenNgay>30/06/2025</kyKKhaiDenNgay>
      </KyKKhaiThue>
    </TKhaiThue>
    <NNT><mst>0000000000</mst><tenNNT>CONG TY X</tenNNT></NNT></TTinTKhaiThue></TTinChung>
    <CTieuTKhaiChinh>
      <ct21>0</ct21>
      <ct22>1.000.000</ct22>
      <GiaTriVaThueGTGTHHDVMuaVao><ct23>500</ct23><ct24></ct24></GiaTriVaThueGTGTHHDVMuaVao>
      <ct43>-100</ct43>
      <Header><ct09/></Header>
    </CTieuTKhaiChinh>
    <PLuc><BangKeTenHHDV><ct21>999999</ct21><ct22>888888</ct22></BangKeTenHHDV></PLuc>
  </HSoKhaiThue>
</HSoThueDTu>"""

NOTICE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<TBao><DLTBao><PBan>2.1.0</PBan><MSo>04/SS-HDDT</MSo>
<Ten>Thong bao</Ten><MST>0000000000</MST></DLTBao></TBao>"""


def registry_with_gtgt() -> MappingRegistry:
    registry = MappingRegistry()
    registry.add(
        FormMapping(
            mapping_id="GTGT_842_v2.8.3",
            mapping_version="1",
            form_code="842",
            form_version="2.8.3",
            tax_type="GTGT",
            fields={
                "vat_payable": FieldMapping(
                    canonical_name="vat_payable",
                    indicator_code="ct43",
                    display_name="Thuế GTGT phải nộp",
                    xpath="CTieuTKhaiChinh/ct43",
                ),
                "total_revenue": FieldMapping(
                    canonical_name="total_revenue",
                    indicator_code="ct22",
                    display_name="Doanh thu",
                    xpath="CTieuTKhaiChinh/ct22",
                ),
            },
        )
    )
    return registry


class ExtractTests(unittest.TestCase):
    def test_metadata_and_indicators(self) -> None:
        decl = extract_declaration(RETURN_XML)
        self.assertEqual(decl.status, "NEED_MAPPING")
        self.assertEqual(decl.form_code, "842")
        self.assertEqual(decl.form_version, "2.8.3")
        self.assertEqual(decl.tax_type_hint, "GTGT")
        self.assertEqual(decl.filing_type, "B")
        self.assertEqual(decl.supplement_number, "1")
        self.assertEqual(decl.taxpayer.tax_code, "0000000000")
        self.assertEqual(decl.period.raw, "06/2025")
        self.assertEqual(decl.period.period_type, "M")
        self.assertEqual(decl.period.year, 2025)
        self.assertEqual(decl.period.month, 6)
        self.assertIn("MAPPING_NOT_FOUND", decl.warnings)

    def test_indicator_values_and_provenance(self) -> None:
        decl = extract_declaration(RETURN_XML)
        self.assertEqual(decl.indicator("ct21").value, "0")
        self.assertEqual(decl.indicator("ct22").value, "1000000")  # bỏ dấu chấm
        self.assertIsNone(decl.indicator("ct24").value)  # rỗng = NULL, không phải 0
        self.assertEqual(decl.indicator("ct43").value, "-100")  # giữ dấu âm
        self.assertEqual(
            decl.indicator("ct23").xpath,
            "/HSoThueDTu/HSoKhaiThue/CTieuTKhaiChinh/GiaTriVaThueGTGTHHDVMuaVao/ct23",
        )
        self.assertEqual(decl.indicator("ct43").status, "NEED_MAPPING")
        self.assertIsNone(decl.indicator("ct43").canonical_name)

    def test_quarter_period_is_normalized_only_when_explicit(self) -> None:
        quarterly = RETURN_XML.replace(
            b"<kieuKy>M</kieuKy><kyKKhai>06/2025</kyKKhai>",
            b"<kieuKy>Q</kieuKy><kyKKhai>Q2/2025</kyKKhai>",
        )
        decl = extract_declaration(quarterly)
        self.assertEqual(decl.period.raw, "Q2/2025")
        self.assertEqual(decl.period.year, 2025)
        self.assertEqual(decl.period.quarter, 2)
        self.assertIsNone(decl.period.month)

    def test_does_not_extract_detail_table(self) -> None:
        decl = extract_declaration(RETURN_XML)
        # ct21 trong PLuc/BangKeTenHHDV là bảng kê chi tiết → không lấy.
        codes = [item.code for item in decl.indicators]
        self.assertEqual(codes.count("ct21"), 1)
        self.assertEqual(decl.indicator("ct21").value, "0")

    def test_mapping_applied(self) -> None:
        decl = extract_declaration(RETURN_XML, registry=registry_with_gtgt())
        self.assertEqual(decl.status, "MAPPED")
        self.assertEqual(decl.mapping_id, "GTGT_842_v2.8.3")
        payable = decl.indicator("ct43")
        self.assertEqual(payable.status, "MAPPED")
        self.assertEqual(payable.canonical_name, "vat_payable")
        self.assertEqual(payable.display_name, "Thuế GTGT phải nộp")

    def test_unknown_version_not_auto_mapped(self) -> None:
        # Cùng mã mẫu nhưng version khác → KHÔNG tự áp mapping version gần nhất.
        unknown = RETURN_XML.replace(b"2.8.3", b"9.9.9")
        decl = extract_declaration(unknown, registry=registry_with_gtgt())
        self.assertEqual(decl.status, "NEED_MAPPING")

    def test_versionless_mapping_applies_to_all_versions(self) -> None:
        # Mapping khai form_version=null áp cho mọi phiên bản của mã mẫu.
        registry = MappingRegistry()
        registry.add(
            FormMapping(
                mapping_id="GTGT_842_any",
                mapping_version="1",
                form_code="842",
                form_version=None,
                fields={
                    "vat_payable": FieldMapping(
                        canonical_name="vat_payable",
                        indicator_code="ct43",
                        xpath="CTieuTKhaiChinh/ct43",
                    )
                },
            )
        )
        unknown = RETURN_XML.replace(b"2.8.3", b"9.9.9")
        decl = extract_declaration(unknown, registry=registry)
        self.assertEqual(decl.status, "MAPPED")
        self.assertEqual(decl.indicator("ct43").value, "-100")

    def test_missing_mapped_indicator_keeps_null(self) -> None:
        registry = MappingRegistry()
        registry.add(
            FormMapping(
                mapping_id="GTGT_842",
                mapping_version="1",
                form_code="842",
                form_version=None,
                fields={
                    "ct99": FieldMapping(
                        canonical_name="ct99",
                        indicator_code="ct99",
                        xpath="CTieuTKhaiChinh/ct99",
                    )
                },
            )
        )
        decl = extract_declaration(RETURN_XML, registry=registry)
        missing = decl.indicator("ct99")
        self.assertIsNone(missing.value)
        self.assertIn("MISSING_IN_XML", missing.warnings)

    def test_notice_without_namespace(self) -> None:
        decl = extract_declaration(NOTICE_XML)
        self.assertEqual(decl.form_code, "04/SS-HDDT")
        self.assertEqual(decl.taxpayer.tax_code, "0000000000")

    def test_invalid_xml_returns_error(self) -> None:
        decl = extract_declaration(b"<a><b></a>")
        self.assertEqual(decl.status, "error")
        self.assertIn("INVALID_XML", decl.error or "")

    def test_error_keeps_source_reference(self) -> None:
        decl = extract_declaration(
            b"<broken>",
            artifact_id="a1",
            source_zip="z.zip",
            source_inner_file="x.xml",
            source_sha256="deadbeef",
        )
        self.assertEqual(decl.artifact_id, "a1")
        self.assertEqual(decl.source_zip, "z.zip")
        self.assertEqual(decl.source_sha256, "deadbeef")


class GtgtGoldenTests(unittest.TestCase):
    """Golden test cho mẫu 01/GTGT (mã 842) với fixture ẩn danh."""

    def test_matches_golden(self) -> None:
        data = (FIXTURES / "gtgt_842_return.xml").read_bytes()
        golden = json.loads((FIXTURES / "gtgt_842_return.golden.json").read_text("utf-8"))
        decl = extract_declaration(data, registry=load_registry())
        self.assertEqual(decl.form_code, golden["form_code"])
        self.assertEqual(decl.form_version, golden["form_version"])
        self.assertEqual(decl.tax_type_hint, golden["tax_type_hint"])
        self.assertEqual(decl.filing_type, golden["filing_type"])
        self.assertEqual(decl.supplement_number, golden["supplement_number"])
        self.assertEqual(decl.status, golden["status"])
        self.assertEqual(decl.mapping_id, golden["mapping_id"])
        self.assertEqual(decl.taxpayer.tax_code, golden["taxpayer_tax_code"])
        self.assertEqual(decl.period.raw, golden["period_raw"])
        self.assertEqual(decl.period.period_type, golden["period_type"])
        for code, expected in golden["indicators"].items():
            indicator = decl.indicator(code)
            self.assertIsNotNone(indicator, f"thiếu chỉ tiêu {code}")
            self.assertEqual(indicator.value, expected, f"sai giá trị {code}")
            self.assertEqual(indicator.status, "MAPPED", f"{code} chưa MAPPED")
            self.assertTrue(indicator.xpath.startswith(".//CTieuTKhaiChinh"))

    def test_detail_table_not_extracted(self) -> None:
        data = (FIXTURES / "gtgt_842_return.xml").read_bytes()
        decl = extract_declaration(data, registry=load_registry())
        codes = [item.code for item in decl.indicators]
        self.assertEqual(len(codes), len(set(codes)))  # không trùng mã


class ManifestReaderTests(unittest.TestCase):
    def test_zip_doi_duoi_van_doc_member_theo_format_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "archive.data"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("return.xml", RETURN_XML)
            manifest = {
                "containers": [
                    {
                        "rel_path": archive_path.name,
                        "format": "zip",
                        "members": [
                            {
                                "artifact_id": "artifact-1",
                                "member_name": "return.xml",
                                "format": "xml",
                                "status": "ok",
                                "sha256": hashlib.sha256(RETURN_XML).hexdigest(),
                            }
                        ],
                    }
                ]
            }

            results = parse_manifest(manifest, root, registry=registry_with_gtgt())

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["form_code"], "842")
            self.assertNotEqual(results[0]["status"], "error")

    def test_changed_or_missing_source_is_reported_without_parsing_new_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'return.xml'
            manifest = {'containers': [{'rel_path': path.name, 'format': 'xml', 'members': [{
                'artifact_id': 'fixture', 'member_name': path.name, 'format': 'xml', 'status': 'ok',
                'sha256': hashlib.sha256(RETURN_XML).hexdigest()}]}]}
            path.write_bytes(RETURN_XML + b'\n')
            changed = parse_manifest(manifest, root)[0]
            self.assertEqual(changed['status'], 'error')
            self.assertIn('SOURCE_CHANGED', changed['error'])
            self.assertEqual(changed['indicators'], [])
            path.unlink()
            missing = parse_manifest(manifest, root)[0]
            self.assertEqual(missing['status'], 'error')
            self.assertIn('SOURCE_UNREADABLE', missing['error'])

    def test_manifest_cannot_read_outside_root_or_bypass_xml_size_limit(self):
        from unittest.mock import patch

        from gdt_tax.parser.cli import _read_member_bytes
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / 'source'
            root.mkdir()
            (base / 'outside.xml').write_bytes(RETURN_XML)
            (root / 'large.xml').write_bytes(RETURN_XML)
            self.assertIsNone(_read_member_bytes(root, '../outside.xml', '', is_archive=False))
            self.assertIsNone(_read_member_bytes(root, str(base / 'outside.xml'), '', is_archive=False))
            with patch('gdt_tax.parser.cli.MAX_XML_BYTES', 8):
                self.assertIsNone(_read_member_bytes(root, 'large.xml', '', is_archive=False))
                with zipfile.ZipFile(root / 'large.zip', 'w') as archive:
                    archive.writestr('large.xml', RETURN_XML)
                self.assertIsNone(_read_member_bytes(root, 'large.zip', 'large.xml', is_archive=True))


class TncnGoldenTests(unittest.TestCase):
    """Golden cho 05/KK-TNCN: TT80 (mã 864) và TT92 (mã 394) là hai mapping riêng."""

    def _check(self, stem: str) -> None:
        data = (FIXTURES / f"{stem}.xml").read_bytes()
        golden = json.loads((FIXTURES / f"{stem}.golden.json").read_text("utf-8"))
        decl = extract_declaration(data, registry=load_registry())
        self.assertEqual(decl.form_code, golden["form_code"])
        self.assertEqual(decl.form_version, golden["form_version"])
        self.assertEqual(decl.status, golden["status"])
        self.assertEqual(decl.mapping_id, golden["mapping_id"])
        for code, expected in golden["indicators"].items():
            indicator = decl.indicator(code)
            self.assertIsNotNone(indicator, f"thiếu chỉ tiêu {code}")
            self.assertEqual(indicator.value, expected, f"sai giá trị {code}")
            self.assertEqual(indicator.status, "MAPPED")

    def test_tt80_864(self) -> None:
        self._check("tncn_864_05kk_tt80")

    def test_tt92_394(self) -> None:
        self._check("tncn_394_05kk_tt92")

    def test_same_code_number_different_meaning(self) -> None:
        # [21] ở 394 là Tổng số người lao động; ở 864 là Tổng TNCT trả cho cá nhân.
        tt92 = extract_declaration(
            (FIXTURES / "tncn_394_05kk_tt92.xml").read_bytes(), registry=load_registry()
        )
        tt80 = extract_declaration(
            (FIXTURES / "tncn_864_05kk_tt80.xml").read_bytes(), registry=load_registry()
        )
        self.assertEqual(tt92.indicator("ct21").canonical_name, "employee_count")
        self.assertEqual(tt80.indicator("ct21").canonical_name, "taxable_income_total")


class TndnGoldenTests(unittest.TestCase):
    """Golden cho 03/TNDN mã 892; hai version có cấu trúc C7 khác nhau."""

    def _check(self, stem: str) -> None:
        data = (FIXTURES / f"{stem}.xml").read_bytes()
        golden = json.loads((FIXTURES / f"{stem}.golden.json").read_text("utf-8"))
        decl = extract_declaration(data, registry=load_registry())
        self.assertEqual(decl.form_code, golden["form_code"])
        self.assertEqual(decl.form_version, golden["form_version"])
        self.assertEqual(decl.status, golden["status"])
        self.assertEqual(decl.mapping_id, golden["mapping_id"])
        self.assertEqual(decl.filing_type, golden["filing_type"])
        self.assertEqual(decl.supplement_number, golden["supplement_number"])
        self.assertEqual(decl.taxpayer.tax_code, golden["taxpayer_tax_code"])
        self.assertEqual(decl.period.raw, golden["period_raw"])
        self.assertEqual(decl.period.period_type, golden["period_type"])
        self.assertEqual(decl.period.year, golden["period_year"])
        self.assertEqual(decl.period.period_from, golden["period_from"])
        self.assertEqual(decl.period.period_to, golden["period_to"])
        for code, expected in golden["indicators"].items():
            indicator = decl.indicator(code)
            self.assertIsNotNone(indicator, f"thiếu chỉ tiêu {code}")
            self.assertEqual(indicator.value, expected, f"sai giá trị {code}")
            self.assertEqual(indicator.status, "MAPPED")
        # BCTC/phụ lục có mã trùng không được ghi đè tờ khai chính.
        self.assertEqual(decl.indicator("ctA1").value, "-1000")
        self.assertNotIn("999999999", [item.value for item in decl.indicators])

    def test_v2_5_1_official(self) -> None:
        self._check("tndn_892_03tndn_v2.5.1")

    def test_v2_9_4_supplemental_and_dynamic_c7(self) -> None:
        self._check("tndn_892_03tndn_v2.9.4")
        decl = extract_declaration(
            (FIXTURES / "tndn_892_03tndn_v2.9.4.xml").read_bytes(),
            registry=load_registry(),
        )
        label = decl.indicator("ctC7_tenThueSuat")
        self.assertEqual(label.value_type, "string")
        self.assertEqual(label.value, "Thuế suất phổ thông")
        self.assertEqual(label.warnings, [])

    def test_unverified_892_version_is_not_mapped(self) -> None:
        data = (FIXTURES / "tndn_892_03tndn_v2.9.4.xml").read_bytes()
        decl = extract_declaration(data.replace(b"2.9.4", b"9.9.9"), registry=load_registry())
        self.assertEqual(decl.status, "NEED_MAPPING")
        self.assertIn("MAPPING_NOT_FOUND", decl.warnings)


class NormalizeNumberTests(unittest.TestCase):
    def test_vietnamese_and_western_formats(self) -> None:
        self.assertEqual(normalize_number("1.234.567")[0], "1234567")
        self.assertEqual(normalize_number("1,234.56")[0], "1234.56")
        self.assertEqual(normalize_number("1234,56")[0], "1234.56")
        self.assertEqual(normalize_number("-100")[0], "-100")
        self.assertEqual(normalize_number("")[0], None)
        self.assertEqual(normalize_number(None)[0], None)

    def test_bad_number_is_error_not_zero(self) -> None:
        value, warning = normalize_number("abc")
        self.assertIsNone(value)
        self.assertEqual(warning, "PARSE_VALUE_ERROR")


class RegistryTests(unittest.TestCase):
    def test_load_from_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            forms = Path(tmp)
            (forms / "gtgt.json").write_text(
                json.dumps(
                    {
                        "mapping_id": "GTGT_842",
                        "mapping_version": "1",
                        "form_code": "842",
                        "form_version": "2.8.3",
                        "fields": {
                            "vat_payable": {"indicator_code": "ct43"}
                        },
                    }
                ),
                encoding="utf-8",
            )
            registry = load_registry(forms)
            self.assertEqual(len(registry), 1)
            found = registry.lookup("842", "2.8.3")
            self.assertIsNotNone(found)
            self.assertEqual(found.field_for_code("ct43").canonical_name, "vat_payable")

    def test_missing_fields_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            forms = Path(tmp)
            (forms / "bad.json").write_text(
                json.dumps({"mapping_id": "x", "form_code": "1"}), encoding="utf-8"
            )
            registry = load_registry(forms)
            self.assertEqual(len(registry), 0)

    def test_default_registry_contains_gtgt_842(self) -> None:
        # Mapping đóng gói thật phải nạp được 01/GTGT (mã 842).
        registry = load_registry()
        self.assertGreaterEqual(len(registry), 1)
        mapping = registry.lookup("842", "2.8.3")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.tax_type, "GTGT")
        self.assertEqual(mapping.field_for_code("ct43").canonical_name, "vat_carried_forward")

    def test_default_registry_contains_tndn_892_verified_versions(self) -> None:
        registry = load_registry()
        old = registry.lookup("892", "2.5.1")
        current = registry.lookup("892", "2.9.4")
        self.assertIsNotNone(old)
        self.assertIsNotNone(current)
        self.assertEqual(old.tax_type, "TNDN")
        self.assertEqual(old.field_for_code("ctC7").canonical_name, "taxable_income_rate_20")
        self.assertEqual(
            current.field_for_code("ctC7_thuNhap").canonical_name,
            "taxable_income_primary_rate",
        )


if __name__ == "__main__":
    unittest.main()
