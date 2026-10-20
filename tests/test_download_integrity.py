"""CORE-12/13 synthetic boundary and resume fixtures, with no portal calls."""
from __future__ import annotations

import base64
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

from desktop.documents import verify_rows
from gdt_tax.dvc_notices import DvcNotice, NoticeFile, NoticeStore, decode_notice_response
from gdt_tax.gnt.models import GiayNopTien
from gdt_tax.gnt.portal import is_gnt_xml
from gdt_tax.gnt.storage import GntStore
from gdt_tax.integrity import evidence_path, validate_pdf, validate_tax_zip, validate_xml
from gdt_tax.inventory import scan_directory
from gdt_tax.models import CaseRecord
from gdt_tax.storage import ZipStore, valid_zip
from gdt_tax.tb.portal import is_tb_pdf
from tests.support import FakeResponse, cleanup_temporary_directory, sample_zip

GNT = b"<CHUNGTU><ID_CTU>synthetic-1</ID_CTU></CHUNGTU>"
NOTICE = b"<TBao><MaTB>synthetic-1</MaTB></TBao>"
PDF = (Path(__file__).parent / "fixtures" / "tb_notice.pdf").read_bytes()


@contextmanager
def fixture_directory():
    temporary = tempfile.TemporaryDirectory()
    try:
        yield temporary.name
    finally:
        cleanup_temporary_directory(temporary)


class DownloadIntegrityTests(unittest.TestCase):
    def test_unknown_xml_and_business_error_envelopes_are_unsupported(self):
        for data in (b"<status><message>failed</message></status>", b"<Envelope/>", b"<error/>", b"<html/>"):
            self.assertFalse(is_gnt_xml(data))
            self.assertFalse(validate_xml(data, "declaration").ok)
        self.assertTrue(is_gnt_xml(GNT))
        self.assertEqual(validate_xml(b'<CHUNGTU xmlns="urn:new"/>', "gnt").status, "UNSUPPORTED")

    def test_dtd_deep_tree_and_invalid_syntax_share_rejections(self):
        for data in (b'<!DOCTYPE CHUNGTU [<!ENTITY x "bad">]><CHUNGTU>&x;</CHUNGTU>',
                     b"<CHUNGTU>" + b"<a>" * 101 + b"</a>" * 101 + b"</CHUNGTU>", b"<CHUNGTU>"):
            self.assertFalse(is_gnt_xml(data))
            self.assertFalse(validate_xml(data, "declaration").ok)

    def test_pdf_requires_xref_and_page_tree_and_rejects_encrypted(self):
        self.assertTrue(is_tb_pdf(PDF))
        for data in (b"%PDF-1.4", b"%PDF-1.4\n%%EOF", PDF[:60], PDF[:-20],
                     PDF.replace(b"/Root 3 0 R", b"/Root 9 0 R")):
            self.assertFalse(validate_pdf(data).ok)
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("synthetic-secret")
        stream = BytesIO()
        writer.write(stream)
        self.assertEqual(validate_pdf(stream.getvalue()).status, "UNSUPPORTED")

    def test_archive_crc_is_distinct_from_document_kind(self):
        data = sample_zip(b"<status><message>failed</message></status>")
        self.assertTrue(valid_zip(data))
        self.assertFalse(validate_tax_zip(data).ok)
        self.assertTrue(validate_tax_zip(sample_zip()).ok)
        with fixture_directory() as tmp:
            self.assertIsNone(ZipStore(tmp).save(CaseRecord("id", "ETAX"), data))

    def test_hash_evidence_is_checked_on_resume_and_desktop(self):
        with fixture_directory() as tmp:
            root = Path(tmp)
            store = GntStore(root)
            record = GiayNopTien(ctu_id="synthetic-1")
            path = store.save(record, GNT)
            self.assertTrue(evidence_path(path).is_file())
            self.assertEqual(store.find_existing(record), path)
            path.write_bytes(GNT.replace(b"synthetic-1", b"synthetic-2"))
            self.assertIsNone(store.find_existing(record))
            row = verify_rows("gnt", [record.to_dict()], root)[0]
            self.assertNotEqual(row["_file_status"], "downloaded")

    def test_corrupt_original_is_preserved_and_new_file_can_resume(self):
        with fixture_directory() as tmp:
            store = GntStore(tmp)
            record = GiayNopTien(ctu_id="synthetic-1")
            old = store.path_for(record)
            old.write_bytes(b"suspect-original")
            saved = store.save(record, GNT)
            self.assertNotEqual(saved, old)
            self.assertEqual(old.read_bytes(), b"suspect-original")
            self.assertEqual(store.find_existing(GiayNopTien(ctu_id="synthetic-1")), saved)

    def test_notice_html_declared_xml_and_one_byte_never_save_or_resume(self):
        for data in (b"<html>failed</html>", b"<status>failed</status>", b"x", b"<TBao>", b"%PDF-1.4"):
            response = FakeResponse(json_payload={"fileType": "xml", "content": base64.b64encode(data).decode()})
            self.assertIsNone(decode_notice_response(response))
            with fixture_directory() as tmp:
                store = NoticeStore(tmp)
                self.assertIsNone(store.save("case", DvcNotice("notice"), NoticeFile("x.xml", data, "xml")))
        decoded = decode_notice_response(FakeResponse(json_payload={"fileType": "xml", "content": base64.b64encode(NOTICE).decode()}))
        self.assertEqual(decoded.data, NOTICE)

    def test_notice_source_route_evidence_prevents_same_id_reuse(self):
        with fixture_directory() as tmp:
            store = NoticeStore(tmp)
            dvc = DvcNotice("same-id", title="synthetic notice")
            tdt = replace(dvc, is_tdt=True)
            payload = NoticeFile("notice.xml", NOTICE, "xml")
            first = store.save("case", dvc, payload)
            self.assertIsNone(store.find_existing("case", tdt))
            second = store.save("case", tdt, payload)
            self.assertNotEqual(first, second)
            self.assertEqual(store.find_existing("case", dvc), first)
            self.assertEqual(store.find_existing("case", tdt), second)
            self.assertIsNone(store.find_existing("case", "same-id"))

    def test_notice_base64_length_checked_before_decode(self):
        with patch("gdt_tax.dvc_notices.MAX_NOTICE_BYTES", 3), patch("gdt_tax.dvc_notices.base64.b64decode") as decode:
            self.assertIsNone(decode_notice_response(FakeResponse(json_payload={"content": "a" * 100})))
            decode.assert_not_called()

    def test_integrity_sidecars_are_not_inventory_sources(self):
        with fixture_directory() as tmp:
            root = Path(tmp)
            GntStore(root).save(GiayNopTien(ctu_id="synthetic-1"), GNT)
            manifest = scan_directory(root)
            self.assertEqual(len(manifest.containers), 1)
            self.assertEqual(manifest.containers[0].format, "xml")
