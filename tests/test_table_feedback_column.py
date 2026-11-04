"""S03: cột "Phản hồi CQT" và trạng thái CQT tách khỏi trạng thái tải."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class FeedbackColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.table_model import RecordsModel
        self.model = RecordsModel()
        self.model.reset('tax', [])

    def column(self, key: str) -> int:
        from desktop.table_model import COLUMNS
        return next(index for index, (name, _) in enumerate(COLUMNS['tax']) if name == key)

    def cell(self, row: dict, key: str):
        self.model.reset('tax', [row])
        return self.model.index(0, self.column(key))

    @staticmethod
    def row(**extra) -> dict:
        base = {'ma_ho_so': 'case-A', 'nguon': 'DVC', 'trang_thai': '',
                '_file_status': 'not_downloaded'}
        base.update(extra)
        return base

    def test_tax_headers_use_feedback_and_separate_download_terms(self):
        from desktop.table_model import COLUMNS
        headers = dict(COLUMNS['tax'])
        self.assertEqual(headers['_notice_state'], 'Phản hồi CQT')
        self.assertEqual(headers['trang_thai'], 'Trạng thái CQT')
        self.assertEqual(headers['_file_status'], 'Trạng thái tải')
        self.assertNotIn('Thông báo', headers.values())
        self.assertNotIn('Tệp ZIP', headers.values())

    def test_feedback_column_shows_zero_one_and_n(self):
        self.assertEqual(self.cell(self.row(), '_notice_state').data(), 'Chưa có phản hồi')
        one = self.cell(self.row(_notices=[{'name': 'a.xml'}]), '_notice_state')
        self.assertEqual(one.data(), 'Xem phản hồi (1)')
        two = self.cell(self.row(_notices=[{'name': 'a.xml'}, {'name': 'b.xml'}]), '_notice_state')
        self.assertEqual(two.data(), 'Xem phản hồi (2)')

    def test_feedback_column_never_renders_file_count_jargon(self):
        index = self.cell(self.row(_notices=[{'name': 'a.xml'}, {'name': 'b.xml'}]), '_notice_state')
        for forbidden in ('Mở 2 tệp', 'Mở 1 tệp', 'tệp'):
            self.assertNotIn(forbidden, index.data())

    def test_downloaded_zip_is_not_a_cqt_verdict(self):
        row = self.row(_notices=[], _file_status='downloaded', trang_thai='')
        self.assertEqual(self.cell(row, 'trang_thai').data(), 'Chưa xác định')
        self.assertEqual(self.cell(row, '_file_status').data(), 'Đã tải')

    def test_cqt_status_prioritizes_portal_text_and_falls_back_to_xml(self):
        row = self.row(_notice_state='rejected', trang_thai='Đã chấp nhận',
                       _notices=[{'name': 'reject.xml'}])
        self.assertEqual(self.cell(row, 'trang_thai').data(), 'Đã chấp nhận')
        accepted = self.row(_notice_state='accepted', trang_thai='',
                            _notices=[{'name': 'accept.xml'}])
        self.assertEqual(self.cell(accepted, 'trang_thai').data(), 'Đã chấp nhận')

    def test_conflicting_results_are_flagged_for_review(self):
        row = self.row(_notices=[{'name': 'a.xml'}], _feedback_conflict=True)
        self.assertEqual(self.cell(row, 'trang_thai').data(), 'Cần kiểm tra')

    def test_tooltips_explain_feedback_and_independence(self):
        from PySide6.QtCore import Qt
        feedback = self.cell(self.row(_notices=[{'name': 'a.xml'}]), '_notice_state')
        self.assertIn('Bấm để xem phản hồi', feedback.data(Qt.ItemDataRole.ToolTipRole))
        empty = self.cell(self.row(), '_notice_state')
        self.assertIn('chưa kết luận cổng không có thông báo',
                      empty.data(Qt.ItemDataRole.ToolTipRole))
        status_tip = self.model.headerData(self.column('trang_thai'), Qt.Orientation.Horizontal,
                                           Qt.ItemDataRole.ToolTipRole)
        self.assertIn('độc lập với trạng thái tải', status_tip)
        feedback_tip = self.model.headerData(self.column('_notice_state'), Qt.Orientation.Horizontal,
                                             Qt.ItemDataRole.ToolTipRole)
        self.assertIn('Phản hồi của cơ quan thuế', feedback_tip)


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class VerifiedRowStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_verify_rows_sets_cqt_status_from_rejected_notice(self):
        from desktop.documents import verify_rows
        from gdt_tax.constants import SOURCE_DVC
        from gdt_tax.models import CaseRecord

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'thong-bao-dinh-kem' / 'case-A'
            folder.mkdir(parents=True)
            (folder / 'reject.xml').write_bytes(
                '<TBaoThueDTu><TBaoThue><TTinTBaoThue><tenTBao>Không chấp nhận hồ sơ</tenTBao>'
                '<soTBao>9/TB</soTBao></TTinTBaoThue><NDungTBao><trangThai>N</trangThai>'
                '</NDungTBao></TBaoThue></TBaoThueDTu>'.encode())
            row = verify_rows('tax', [CaseRecord('case-A', SOURCE_DVC).to_dict()], root)[0]
            self.assertEqual(row['_cqt_status'], 'rejected')
            self.assertEqual(row['_cqt_status_label'], 'Không chấp nhận')
            self.assertEqual(row['_feedback_count'], 1)
            self.assertFalse(row['_feedback_conflict'])

    def test_verify_rows_reads_accepted_result_from_single_xml(self):
        from desktop.documents import verify_rows
        from gdt_tax.constants import SOURCE_DVC
        from gdt_tax.models import CaseRecord

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'thong-bao-dinh-kem' / 'case-B'
            folder.mkdir(parents=True)
            (folder / 'result.xml').write_bytes(
                '<TBaoThueDTu><TBaoThue><TTinTBaoThue>'
                '<tenTBao>Thông báo tiếp nhận hồ sơ khai thuế</tenTBao>'
                '<soTBao>9/TB</soTBao><ngayTBao>16/10/2026</ngayTBao>'
                '</TTinTBaoThue><NDungTBao><trangThai>Đã chấp nhận</trangThai>'
                '</NDungTBao></TBaoThue></TBaoThueDTu>'.encode())
            row = verify_rows('tax', [CaseRecord('case-B', SOURCE_DVC).to_dict()], root)[0]
            self.assertEqual(row['_notice_state'], 'accepted')
            self.assertEqual(row['_cqt_status_label'], 'Đã chấp nhận')


if __name__ == '__main__':
    unittest.main()
