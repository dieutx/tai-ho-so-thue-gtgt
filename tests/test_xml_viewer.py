"""S05: XML Viewer an toàn, hai chế độ, dùng chung hai nguồn."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None

from desktop.domain import (  # noqa: E402
    BUSINESS_ACCEPTED,
    OWNER_FEEDBACK,
    OWNER_TAX_NOTICE,
    DocumentAsset,
    SubmissionFeedback,
    TaxNotice,
)
from desktop.xml_viewer import (  # noqa: E402
    contains_dtd,
    decode_xml,
    detect_encoding,
    readable_fields,
)
from gdt_tax.parser.xml_reader import parse_xml  # noqa: E402

XML = ('<?xml version="1.0" encoding="UTF-8"?>'
       '<TBaoThueDTu xmlns="http://kekhaithue.gdt.gov.vn/TBaoThue"><TBaoThue>'
       '<TTinTBaoThue><maTBao>844</maTBao><tenTBao>Chấp nhận hồ sơ</tenTBao>'
       '<soTBao>298/TB</soTBao><ngayTBao>19/10/2026</ngayTBao></TTinTBaoThue>'
       '<NDungTBao><trangThai>Y</trangThai><LyDo>Hồ sơ hợp lệ</LyDo></NDungTBao>'
       '</TBaoThue></TBaoThueDTu>')


def asset(path: Path, content_type: str = 'application/xml') -> DocumentAsset:
    return DocumentAsset(asset_key='asset-1', owner_kind=OWNER_FEEDBACK, owner_key='sub-1',
                         path_or_handle=str(path), original_filename=path.name,
                         content_type=content_type, checksum='abc', size=len(path.read_bytes()))


class ParsingTests(unittest.TestCase):
    def test_detect_encoding_bom_declaration_and_default(self):
        self.assertEqual(detect_encoding(b'\xef\xbb\xbf<a/>'), 'utf-8-sig')
        self.assertEqual(detect_encoding(b'\xff\xfe<\x00a\x00/\x00>\x00'), 'utf-16')
        self.assertEqual(detect_encoding(b'<?xml version="1.0" encoding="ISO-8859-1"?><a/>'),
                         'ISO-8859-1')
        self.assertEqual(detect_encoding(b'<a/>'), 'utf-8')

    def test_decode_utf16_keeps_vietnamese(self):
        data = XML.encode('utf-16')
        text, encoding = decode_xml(data)
        self.assertEqual(encoding, 'utf-16')
        self.assertIn('Chấp nhận hồ sơ', text)

    def test_readable_fields_handle_namespace_and_unicode(self):
        fields = readable_fields(parse_xml(XML.encode()))
        self.assertEqual(fields['Số thông báo'], '298/TB')
        self.assertEqual(fields['Tên thông báo'], 'Chấp nhận hồ sơ')
        self.assertEqual(fields['Lý do'], 'Hồ sơ hợp lệ')
        self.assertEqual(fields['Ngày thông báo'], '19/10/2026')

    def test_contains_dtd_detects_doctype_and_entity(self):
        payload = (b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
                   b'<TBaoThueDTu>&xxe;</TBaoThueDTu>')
        self.assertTrue(contains_dtd(payload))
        self.assertFalse(contains_dtd(b'<TBaoThueDTu/>'))


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.xml_viewer import XmlViewer
        self.viewer_class = XmlViewer
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def summary(self) -> SubmissionFeedback:
        return SubmissionFeedback(feedback_key='f-1', submission_key='sub-1',
                                  feedback_type=BUSINESS_ACCEPTED, notice_number='298/TB',
                                  issued_at='19/10/2026', business_result=BUSINESS_ACCEPTED)

    def test_viewer_defaults_to_readable_tab_and_keeps_raw_xml(self):
        source = self.write('tb.xml', XML.encode())
        viewer = self.viewer_class(None, asset(source), source_kind=OWNER_FEEDBACK,
                                   summary=self.summary())
        self.assertEqual(viewer.tabs.currentIndex(), 0)
        self.assertIn('Phản hồi CQT', viewer.title_label.text())
        self.assertIn('298/TB', viewer.title_label.text())
        self.assertTrue(viewer.raw.toPlainText() == XML)
        self.assertIn('Số thông báo', viewer.readable.toPlainText())
        self.assertIn('298/TB', viewer.readable.toPlainText())
        self.assertIn('Đã chấp nhận', viewer.readable.toPlainText())
        viewer.copy_xml()
        from PySide6.QtWidgets import QApplication
        self.assertEqual(QApplication.clipboard().text(), XML)
        self.assertEqual(source.read_bytes(), XML.encode())

    def test_viewer_uses_source_kind_instead_of_mixing_modules(self):
        source = self.write('tb.xml', XML.encode())
        notice = TaxNotice(tax_notice_key='tax_notice::msg-1', notice_type='Thông báo nộp thuế',
                           number='999/TB', issued_at='20/10/2026')
        tax_asset = DocumentAsset(asset_key='n-1', owner_kind=OWNER_TAX_NOTICE,
                                  owner_key='tax_notice::msg-1', path_or_handle=str(source),
                                  original_filename=source.name, content_type='application/xml')
        viewer = self.viewer_class(None, tax_asset, source_kind=OWNER_TAX_NOTICE, summary=notice)
        self.assertIn('Thông báo thuế', viewer.title_label.text())
        self.assertIn('999/TB', viewer.title_label.text())
        self.assertIn('tax_notice', viewer.identity.text())

    def test_non_xml_file_is_not_presented_as_readable_xml(self):
        source = self.write('notice.pdf', b'%PDF-1.4\nfixture')
        viewer = self.viewer_class(None, asset(source, 'application/pdf'),
                                   source_kind=OWNER_FEEDBACK, summary=self.summary())
        self.assertFalse(viewer.is_xml)
        self.assertFalse(viewer.copy_button.isEnabled())
        self.assertEqual(viewer.save_button.text(), 'Lưu tệp')
        self.assertIn('Chưa hỗ trợ trình bày nội dung này', viewer.readable.toPlainText())

    def test_malformed_xml_still_shows_raw(self):
        source = self.write('broken.xml', b'<broken>')
        viewer = self.viewer_class(None, asset(source), source_kind=OWNER_FEEDBACK,
                                   summary=self.summary())
        self.assertEqual(viewer.raw.toPlainText(), '<broken>')
        self.assertIn('XML gốc', viewer.readable.toPlainText())

    def test_unknown_schema_falls_back_without_inventing_fields(self):
        source = self.write('other.xml', b'<Other><foo>bar</foo></Other>')
        viewer = self.viewer_class(None, asset(source), source_kind=OWNER_FEEDBACK,
                                   summary=self.summary())
        self.assertIn('Chưa hỗ trợ trình bày nội dung này', viewer.readable.toPlainText())
        self.assertNotIn('Số thông báo', viewer.readable.toPlainText())
        self.assertEqual(viewer.raw.toPlainText(), '<Other><foo>bar</foo></Other>')

    def test_missing_file_disables_actions(self):
        viewer = self.viewer_class(None, asset(self.write('tb.xml', XML.encode())),
                                   source_kind=OWNER_FEEDBACK, summary=self.summary())
        viewer.path = self.root / 'gone.xml'
        viewer._load()
        self.assertFalse(viewer.copy_button.isEnabled())
        self.assertFalse(viewer.save_button.isEnabled())
        self.assertFalse(viewer.open_button.isEnabled())
        self.assertIn('không còn tồn tại', viewer.readable.toPlainText())

    def test_large_file_is_not_fully_read(self):
        source = self.write('big.xml', b'<a>' + b'x' * 100 + b'</a>')
        with patch('desktop.xml_viewer.MAX_VIEW_BYTES', 10):
            viewer = self.viewer_class(None, asset(source), source_kind=OWNER_FEEDBACK,
                                       summary=self.summary())
        self.assertIn('lớn hơn', viewer.readable.toPlainText())
        self.assertFalse(viewer.copy_button.isEnabled())

    def test_save_copies_bytes_and_refuses_to_overwrite_source(self):
        source = self.write('tb.xml', XML.encode())
        viewer = self.viewer_class(None, asset(source), source_kind=OWNER_FEEDBACK,
                                   summary=self.summary())
        target = self.root / 'saved.xml'
        with patch('desktop.xml_viewer.QFileDialog.getSaveFileName', return_value=(str(target), 'XML')):
            with patch('desktop.xml_viewer.QMessageBox.information'):
                viewer.save_file()
        self.assertEqual(target.read_bytes(), XML.encode())
        with patch('desktop.xml_viewer.QFileDialog.getSaveFileName', return_value=(str(source), 'XML')):
            with patch('desktop.xml_viewer.QMessageBox.warning') as warning:
                viewer.save_file()
        warning.assert_called_once()
        self.assertEqual(source.read_bytes(), XML.encode())

    def test_external_entity_is_never_resolved_or_rendered(self):
        secret = self.root / 'secret.txt'
        secret.write_text('ROOT-SECRET', encoding='utf-8')
        payload = ('<?xml version="1.0"?>'
                   f'<!DOCTYPE TBaoThueDTu [<!ENTITY xxe SYSTEM "file:///{secret.as_posix()}">]>'
                   '<TBaoThueDTu><TBaoThue><TTinTBaoThue><tenTBao>Chấp nhận</tenTBao>'
                   '</TTinTBaoThue><NDungTBao>&xxe;</NDungTBao></TBaoThue></TBaoThueDTu>').encode()
        source = self.write('xxe.xml', payload)
        viewer = self.viewer_class(None, asset(source), source_kind=OWNER_FEEDBACK,
                                   summary=self.summary())
        self.assertIn('DOCTYPE/ENTITY', viewer.readable.toPlainText())
        self.assertNotIn('ROOT-SECRET', viewer.readable.toPlainText())
        self.assertNotIn('ROOT-SECRET', viewer.raw.toPlainText())
        self.assertEqual(source.read_bytes(), payload)


if __name__ == '__main__':
    unittest.main()
