"""Xem file: tách XML chính từ ZIP hồ sơ, an toàn, dùng lại và không đổi ZIP gốc."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from gdt_tax.declaration_view import DeclarationViewError, declaration_xml
from tests.support import cleanup_temporary_directory

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

DECLARATION = b'<HSoThueDTu><maHoSo>synthetic</maHoSo></HSoThueDTu>'
NOTICE = b'<TBao><maThongBao>synthetic</maThongBao></TBao>'


def make_zip(members: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


class DeclarationXmlTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        cleanup_temporary_directory(self._tmp)

    def store(self, members, name='ho-so.zip'):
        path = self.root / name
        path.write_bytes(make_zip(members))
        return path

    def test_single_xml_is_extracted_once_and_zip_is_unchanged(self):
        source = self.store({'to-khai.xml': DECLARATION})
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        derived = declaration_xml(source)
        self.assertTrue(derived.is_file())
        self.assertEqual(derived.read_bytes(), DECLARATION)
        self.assertEqual(derived.parent, source.parent)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        stamp = derived.stat().st_mtime_ns
        self.assertEqual(declaration_xml(source), derived)
        self.assertEqual(derived.stat().st_mtime_ns, stamp)

    def test_declaration_is_preferred_over_notice_document(self):
        source = self.store({'thong-bao.xml': NOTICE, 'to-khai.xml': DECLARATION})
        self.assertEqual(declaration_xml(source).read_bytes(), DECLARATION)

    def test_two_declarations_are_reported_as_ambiguous(self):
        source = self.store({'a.xml': DECLARATION, 'b.xml': DECLARATION})
        with self.assertRaises(DeclarationViewError) as caught:
            declaration_xml(source)
        self.assertEqual(caught.exception.code, 'ZIP_AMBIGUOUS_DOCUMENTS')
        self.assertIn('a.xml', str(caught.exception))
        self.assertFalse(any(path.suffix == '.xml' for path in self.root.iterdir()))

    def test_traversal_member_is_rejected(self):
        source = self.store({'../evil.xml': DECLARATION})
        with self.assertRaises(DeclarationViewError) as caught:
            declaration_xml(source)
        self.assertEqual(caught.exception.code, 'ZIP_UNSAFE_MEMBER')
        self.assertFalse((self.root.parent / 'evil.xml').exists())

    def test_zip_without_declaration_xml_is_rejected(self):
        source = self.store({'readme.txt': b'khong phai ho so'})
        with self.assertRaises(DeclarationViewError) as caught:
            declaration_xml(source)
        self.assertEqual(caught.exception.code, 'ZIP_DOCUMENT_KIND_MISSING')

    def test_high_compression_ratio_is_rejected(self):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            archive.writestr('to-khai.xml', DECLARATION + b'0' * (4 * 1024 * 1024))
        source = self.root / 'nen-qua-muc.zip'
        source.write_bytes(buffer.getvalue())
        with self.assertRaises(DeclarationViewError) as caught:
            declaration_xml(source)
        self.assertEqual(caught.exception.code, 'ZIP_UNSAFE_OR_INVALID')
        self.assertFalse(any(path.suffix == '.xml' for path in self.root.iterdir()))

    def test_existing_xml_path_is_returned_unchanged(self):
        xml = self.root / 'co-san.xml'
        xml.write_bytes(DECLARATION)
        self.assertEqual(declaration_xml(xml), xml)

    def test_missing_file_is_reported(self):
        with self.assertRaises(DeclarationViewError) as caught:
            declaration_xml(self.root / 'khong-co.zip')
        self.assertEqual(caught.exception.code, 'FILE_MISSING')


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Optional desktop Qt dependencies')
class DeclarationViewUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.settings_store import SettingsStore
        from desktop.ui import MainWindow
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.window = MainWindow(SettingsStore(self.root / 'settings.json'))
        self.source = self.root / 'ho-so.zip'
        self.source.write_bytes(make_zip({'to-khai.xml': DECLARATION}))

    def tearDown(self):
        self.window.close()
        cleanup_temporary_directory(self._tmp)

    def test_action_opens_derived_xml_with_default_application(self):
        self.assertEqual(self.window.mode, 'tax')
        self.window.detail_row = {'_file_path': str(self.source), 'ma_ho_so': 'synthetic'}
        with patch.object(self.window, 'open_path') as opened:
            self.window.open_detail_file()
        opened.assert_called_once()
        self.assertEqual(opened.call_args[0][0].suffix, '.xml')
        self.assertEqual(opened.call_args[0][0].read_bytes(), DECLARATION)


if __name__ == '__main__':
    unittest.main()
