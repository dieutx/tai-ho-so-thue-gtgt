"""S09: gói hồ sơ ZIP đúng owner, an toàn tên tệp; lịch sử thử lại mục lỗi."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None

from desktop.bundle import export_submission_bundle, safe_archive_name  # noqa: E402
from desktop.documents import verify_rows  # noqa: E402
from gdt_tax.constants import SOURCE_DVC  # noqa: E402
from gdt_tax.models import CaseRecord  # noqa: E402
from gdt_tax.storage import ZipStore  # noqa: E402
from tests.support import sample_zip  # noqa: E402


def notice_xml(title: str, number: str) -> bytes:
    return ('<TBaoThueDTu><TBaoThue><TTinTBaoThue><tenTBao>' + title + '</tenTBao>'
            '<soTBao>' + number + '</soTBao><ngayTBao>19/10/2026</ngayTBao>'
            '</TTinTBaoThue><NDungTBao><trangThai>Y</trangThai></NDungTBao>'
            '</TBaoThue></TBaoThueDTu>').encode()


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_row(self, case: str, *, feedback=(), extra_notices=None) -> dict:
        record = CaseRecord(case, SOURCE_DVC, to_khai='01/GTGT', ky_tinh_thue='Quý 3/2026',
                            ngay_nop='20/10/2026')
        ZipStore(self.root).save(record, sample_zip())
        folder = self.root / 'thong-bao-dinh-kem' / case
        folder.mkdir(parents=True, exist_ok=True)
        for name, title, number in feedback:
            (folder / name).write_bytes(notice_xml(title, number))
        row = verify_rows('tax', [record.to_dict()], self.root)[0]
        if extra_notices is not None:
            row['_notices'] = extra_notices
        return row

    def test_bundle_includes_declaration_and_only_its_feedback(self):
        row_a = self.make_row('case-A', feedback=[
            ('tiep-nhan.xml', 'Tiếp nhận hồ sơ', '1/TB'),
            ('chap-nhan.xml', 'Chấp nhận hồ sơ', '2/TB')])
        self.make_row('case-B', feedback=[('other.xml', 'Chấp nhận hồ sơ', '3/TB')])
        (self.root / 'thong-bao').mkdir()
        (self.root / 'thong-bao' / 'doc-lap.pdf').write_bytes(b'%PDF-1.4')
        target = self.root / 'bundle.zip'
        result = export_submission_bundle(row_a, target, taxpayer_key='mst-A')
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read('manifest.json'))
        self.assertTrue(any(name.startswith('to-khai/') for name in names))
        feedback_names = [name for name in names if name.startswith('phan-hoi/')]
        self.assertEqual(len(feedback_names), 2)
        self.assertFalse(any('other.xml' in name for name in names))
        self.assertFalse(any('doc-lap.pdf' in name for name in names))
        self.assertEqual(len(manifest['feedback']), 2)
        self.assertEqual(manifest['declaration']['source_id'], 'case-A')
        self.assertEqual(manifest['submission_key'], 'taxpayer=mst-A::source=DVC::id=case-A::version=')
        self.assertIn('taxpayer=mst-A', result.manifest['submission_key'])

    def test_missing_file_is_reported_not_silently_dropped(self):
        row = {'ma_ho_so': 'case-C', 'nguon': SOURCE_DVC, '_file_status': 'not_downloaded',
               '_file_path': str(self.root / 'missing.zip'),
               '_notices': [{'path': str(self.root / 'missing-feedback.xml'),
                             'name': 'missing-feedback.xml', 'kind': 'chap-nhan',
                             'state': 'accepted', 'read_status': 'PARSED',
                             'relative_path': 'thong-bao-dinh-kem/case-C/missing-feedback.xml'}]}
        with self.assertRaises(ValueError):
            export_submission_bundle(row, self.root / 'empty.zip')
        valid = self.root / 'feedback.xml'
        valid.write_bytes(notice_xml('Chấp nhận hồ sơ', '9/TB'))
        row['_notices'][0]['path'] = str(valid)
        result = export_submission_bundle(row, self.root / 'partial.zip')
        self.assertEqual(len(result.included), 1)
        self.assertEqual(result.missing[0]['kind'], 'to-khai')
        with zipfile.ZipFile(result.path) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        self.assertEqual(manifest['missing'][0]['kind'], 'to-khai')

    def test_duplicate_and_unicode_names_do_not_overwrite(self):
        first = self.root / 'a.xml'
        second = self.root / 'b.xml'
        first.write_bytes(notice_xml('Chấp nhận hồ sơ', '1/TB'))
        second.write_bytes(notice_xml('Chấp nhận hồ sơ', '2/TB'))
        notices = [
            {'path': str(first), 'name': 'Thông báo.xml', 'kind': 'chap-nhan',
             'state': 'accepted', 'read_status': 'PARSED', 'reference_key': 'ref-1',
             'relative_path': 'thong-bao-dinh-kem/case-D/a.xml'},
            {'path': str(second), 'name': 'Thông báo.xml', 'kind': 'chap-nhan',
             'state': 'accepted', 'read_status': 'PARSED', 'reference_key': 'ref-2',
             'relative_path': 'thong-bao-dinh-kem/case-D/b.xml'},
        ]
        row = {'ma_ho_so': 'case-D', 'nguon': SOURCE_DVC, '_file_status': 'not_downloaded',
               '_notices': notices}
        result = export_submission_bundle(row, self.root / 'dup.zip')
        with zipfile.ZipFile(result.path) as archive:
            names = [name for name in archive.namelist() if name.startswith('phan-hoi/')]
        self.assertEqual(len(names), 2)
        self.assertEqual(len(set(names)), 2)
        self.assertTrue(all('Thông báo' in name for name in names))

    def test_archive_names_cannot_traverse(self):
        for raw in ('../evil.xml', '..\\evil.xml', '/etc/passwd', 'C:\\Windows\\evil.xml'):
            name = safe_archive_name(raw)
            self.assertNotIn('/', name)
            self.assertNotIn('\\', name)
            self.assertNotIn('..', name)

    def test_target_cannot_overwrite_source_zip(self):
        row = self.make_row('case-E')
        source = Path(row['_file_path'])
        with self.assertRaises(ValueError):
            export_submission_bundle(row, source)


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class HistoryRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.settings_store import SettingsStore
        from desktop.ui import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = MainWindow(SettingsStore(self.root / 'settings.json'))
        self.window.controller.sessions.set_account('fixture-user', 'fixture-secret')
        self.account_key = hashlib.sha256(b'fixture-user').hexdigest()

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    def test_history_retry_targets_only_failed_rows_of_current_mode(self):
        from desktop.services import JobResult
        rows = [{'ma_ho_so': 'ok', '_file_status': 'downloaded'},
                {'ma_ho_so': 'bad', '_file_status': 'failed'}]
        result = JobResult('PARTIAL', 'x', self.root, rows=rows, account_key=self.account_key,
                           operation='query_and_download', date_range=('01/06/2025', '30/06/2025'))
        with patch.object(self.window, 'download_rows') as download:
            self.window.retry_history_errors(result)
        rows_sent = download.call_args.args[0]
        self.assertEqual([row['ma_ho_so'] for row in rows_sent], ['bad'])

    def test_history_retry_rejects_other_account(self):
        from desktop.services import JobResult
        result = JobResult('PARTIAL', 'x', self.root,
                           rows=[{'ma_ho_so': 'bad', '_file_status': 'failed'}],
                           account_key='other', operation='query_and_download')
        with patch.object(self.window, 'error') as error:
            with patch.object(self.window, 'download_rows') as download:
                self.window.retry_history_errors(result)
        error.assert_called_once()
        download.assert_not_called()

    def test_history_retry_without_failed_rows_is_rejected(self):
        from desktop.services import JobResult
        result = JobResult('SUCCESS', 'x', self.root,
                           rows=[{'ma_ho_so': 'ok', '_file_status': 'downloaded'}],
                           account_key=self.account_key)
        with patch.object(self.window, 'error') as error:
            with patch.object(self.window, 'download_rows') as download:
                self.window.retry_history_errors(result)
        error.assert_called_once()
        download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
