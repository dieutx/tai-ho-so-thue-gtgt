"""Test cho kiểm kê artifact và profile cấu trúc XML (stage 02).

Tất cả chạy offline, dùng fixture tổng hợp trong bộ nhớ — không có hồ sơ thuế
thật, không gọi mạng. Mục tiêu: chứng minh quét đệ quy, một ZIP nhiều member,
an toàn Zip Slip/bomb/mã hóa, nhận diện định dạng từ bytes, và chạy lại
(incremental) không tạo trùng.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from gdt_tax.inventory import (
    INVENTORY_SCHEMA_VERSION,
    build_discovery,
    detect_format,
    load_cache,
    profile_xml,
    scan_directory,
    scan_zip,
    write_discovery,
    write_manifest,
)

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
      <maGiaoDich>GIAODICH-1</maGiaoDich>
    </TKhaiThue>
    <NNT><mst>0000000000</mst><tenNNT>CONG TY CO PHAN X</tenNNT></NNT></TTinTKhaiThue></TTinChung>
    <CTieuTKhaiChinh><ct21>0</ct21><ct22>123456789</ct22></CTieuTKhaiChinh>
  </HSoKhaiThue>
</HSoThueDTu>"""

NOTICE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<TBao><DLTBao Id="_727911"><PBan>2.1.0</PBan><MSo>04/SS-HDDT</MSo>
<Ten>Thong bao hoa don dien tu co sai sot</Ten><MST>0000000000</MST>
<TNNT>CONG TY CO PHAN X</TNNT><NTBao>2026-01-14</NTBao></DLTBao></TBao>"""

OTHER_VERSION_XML = RETURN_XML.replace(b"2.8.3", b"2.5.1").replace(
    b"<CTieuTKhaiChinh><ct21>0</ct21><ct22>123456789</ct22></CTieuTKhaiChinh>",
    b"<CTieuTKhaiChinh><ct21>0</ct21></CTieuTKhaiChinh>",
)


def make_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


class ProfileXmlTests(unittest.TestCase):
    def test_extracts_form_metadata(self) -> None:
        profile = profile_xml(RETURN_XML)
        self.assertEqual(profile.status, "ok")
        self.assertEqual(profile.root_element, "HSoThueDTu")
        self.assertEqual(profile.namespace, "http://kekhaithue.gdt.gov.vn/TKhaiThue")
        self.assertEqual(profile.possible_form_code, "842")
        self.assertEqual(profile.possible_form_version, "2.8.3")
        self.assertEqual(profile.possible_filing_type, "B")
        self.assertEqual(profile.possible_supplement_number, "1")
        self.assertEqual(profile.taxpayer_tax_code, "0000000000")
        self.assertEqual(profile.tax_period_raw, "06/2025")
        self.assertEqual(profile.period_type, "M")
        self.assertEqual(profile.period_from, "01/06/2025")
        self.assertEqual(profile.period_to, "30/06/2025")
        self.assertEqual(profile.possible_tax_type, "GTGT")
        self.assertEqual(profile.reference_candidates["maGiaoDich"], "GIAODICH-1")
        self.assertIsNotNone(profile.structure_signature)

    def test_notice_root_without_namespace(self) -> None:
        profile = profile_xml(NOTICE_XML)
        self.assertEqual(profile.status, "ok")
        self.assertEqual(profile.root_element, "TBao")
        self.assertIsNone(profile.namespace)
        self.assertEqual(profile.possible_form_code, "04/SS-HDDT")

    def test_signature_differs_across_versions(self) -> None:
        first = profile_xml(RETURN_XML).structure_signature
        second = profile_xml(OTHER_VERSION_XML).structure_signature
        self.assertNotEqual(first, second)

    def test_signature_stable_for_same_structure(self) -> None:
        first = profile_xml(RETURN_XML).structure_signature
        second = profile_xml(RETURN_XML).structure_signature
        self.assertEqual(first, second)

    def test_invalid_xml_is_error_not_crash(self) -> None:
        profile = profile_xml(b"<a><b></a>")
        self.assertEqual(profile.status, "error")
        self.assertIn("INVALID_XML", profile.error or "")

    def test_utf16_and_bom(self) -> None:
        for encoding in ("utf-16", "utf-8-sig"):
            with self.subTest(encoding=encoding):
                payload = RETURN_XML.decode("utf-8").encode(encoding)
                self.assertEqual(profile_xml(payload).possible_form_code, "842")


class DetectFormatTests(unittest.TestCase):
    def test_detects_from_bytes_not_extension(self) -> None:
        self.assertEqual(detect_format(b"%PDF-1.7\n"), "pdf")
        self.assertEqual(detect_format(b"PK\x03\x04rest"), "zip")
        self.assertEqual(detect_format(b'<?xml version="1.0"?>'), "xml")
        self.assertEqual(detect_format(b"\x00\x01\x02"), "unknown")


class ScanZipTests(unittest.TestCase):
    def test_multiple_members_and_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.zip"
            path.write_bytes(
                make_zip(
                    {
                        "a.xml": RETURN_XML,
                        "b.xml": OTHER_VERSION_XML,
                        "c.pdf": b"%PDF-1.4 fake",
                    }
                )
            )
            container = scan_zip(path, "case.zip", "deadbeef")
            self.assertEqual(container.status, "ok")
            formats = {member.member_name: member.format for member in container.members}
            self.assertEqual(formats, {"a.xml": "xml", "b.xml": "xml", "c.pdf": "pdf"})
            self.assertNotEqual(
                container.members[0].artifact_id, container.members[1].artifact_id
            )

    def test_zip_slip_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evil.zip"
            path.write_bytes(make_zip({"../../etc/passwd": b"x", "ok.xml": RETURN_XML}))
            container = scan_zip(path, "evil.zip", "deadbeef")
            by_name = {member.member_name: member for member in container.members}
            self.assertEqual(by_name["../../etc/passwd"].status, "error")
            self.assertEqual(by_name["../../etc/passwd"].error, "PATH_TRAVERSAL")
            self.assertEqual(by_name["ok.xml"].status, "ok")

    def test_corrupt_zip_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.zip"
            path.write_bytes(b"PK\x03\x04not really a zip")
            container = scan_zip(path, "broken.zip", "deadbeef")
            self.assertEqual(container.status, "error")
            self.assertIn("CORRUPT_ZIP", container.error or "")

    def test_encrypted_member_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locked.zip"
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("secret.xml", RETURN_XML)
            # Bật cờ mã hóa thủ công (local header offset 6 và central
            # directory offset +8) để mô phỏng ZIP có mật khẩu.
            raw = bytearray(buffer.getvalue())
            raw[6] |= 0x1
            central = raw.find(b"PK\x01\x02")
            raw[central + 8] |= 0x1
            path.write_bytes(bytes(raw))
            container = scan_zip(path, "locked.zip", "deadbeef")
            self.assertEqual(container.members[0].error, "ENCRYPTED")


class ScanDirectoryTests(unittest.TestCase):
    def test_recursive_scan_and_metadata_join(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2025" / "GTGT").mkdir(parents=True)
            (root / "2025" / "GTGT" / "a.zip").write_bytes(make_zip({"a.xml": RETURN_XML}))
            (root / "other").mkdir()
            (root / "other" / "b.zip").write_bytes(make_zip({"b.xml": OTHER_VERSION_XML}))
            metadata = root / "danh_sach_ho_so.json"
            metadata.write_text(
                json.dumps(
                    [
                        {
                            "ma_ho_so": "11320250292528963",
                            "nguon": "ETAX_LEGACY",
                            "to_khai": "01/GTGT",
                            "trang_thai": "Cơ quan thuế chấp nhận hồ sơ khai thuế điện tử của NNT",
                            "tep_zip": "a.zip",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            manifest = scan_directory(root, metadata_path=metadata)
            self.assertEqual(manifest.schema_version, INVENTORY_SCHEMA_VERSION)
            self.assertEqual(manifest.summary["files"], 2)
            self.assertEqual(manifest.summary["containers"], 2)
            self.assertEqual(manifest.summary["xml_members"], 2)
            self.assertEqual(manifest.summary["containers_matched"], 1)
            self.assertEqual(manifest.summary["containers_unmatched"], 1)
            joined = {c.rel_path: c.case for c in manifest.containers}
            self.assertEqual(joined["2025/GTGT/a.zip"]["ma_ho_so"], "11320250292528963")
            self.assertIsNone(joined["other/b.zip"])

    def test_rerun_reuses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.zip").write_bytes(make_zip({"a.xml": RETURN_XML}))
            first = scan_directory(root)
            manifest_path = write_manifest(first, root)
            cache = load_cache(manifest_path)
            self.assertIn("a.zip", cache)
            second = scan_directory(root, cache=cache)
            self.assertEqual(
                first.containers[0].members[0].sha256,
                second.containers[0].members[0].sha256,
            )
            self.assertEqual(second.summary["containers"], 1)

    def test_missing_directory_raises(self) -> None:
        from gdt_tax.errors import GdtError

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(GdtError):
                scan_directory(Path(tmp) / "nope")

    def test_bo_qua_toan_bo_output_do_cong_cu_sinh_ra(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.zip").write_bytes(make_zip({"return.xml": RETURN_XML}))
            for name in (
                "manifest_artifact.json",
                "bao_cao_discovery.json",
                "bao_cao_discovery.md",
                "parsed_declarations.json",
                "phan_loai_artifact.json",
                "Tax_Return_Summary.xlsx",
            ):
                (root / name).write_bytes(b"derived")

            manifest = scan_directory(root)

            self.assertEqual([item.rel_path for item in manifest.containers], ["source.zip"])


class DiscoveryReportTests(unittest.TestCase):
    def test_report_lists_signatures_and_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.zip").write_bytes(make_zip({"a.xml": RETURN_XML}))
            (root / "b.zip").write_bytes(make_zip({"b.xml": OTHER_VERSION_XML}))
            manifest = scan_directory(root)
            report = build_discovery(manifest)
            self.assertEqual(len(report["structure_signatures"]), 2)
            self.assertEqual(report["open_questions"][0]["id"], "A")
            json_path, md_path = write_discovery(report, root)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            text = md_path.read_text(encoding="utf-8")
            self.assertIn("Báo cáo Discovery", text)
            self.assertIn("Câu hỏi mở", text)

    def test_no_source_files_modified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = make_zip({"a.xml": RETURN_XML})
            path = root / "a.zip"
            path.write_bytes(payload)
            before = path.read_bytes()
            scan_directory(root)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
