"""S10: đối soát theo lần nộp, cảnh báo từ chối, CSV/XLSX an toàn."""
from __future__ import annotations

import csv
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from tests.support import cleanup_temporary_directory

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None

from desktop.reconciliation import (  # noqa: E402
    reconciliation_rows,
    write_reconciliation_csv,
    write_reconciliation_xlsx,
)


def notice(path: Path, *, state: str, kind: str, number: str, reason: str = '') -> dict:
    return {'path': str(path), 'name': path.name, 'kind': kind, 'state': state,
            'read_status': 'PARSED', 'reference_key': number,
            'relative_path': f'thong-bao-dinh-kem/case/{path.name}',
            'so_thong_bao': number, 'ngay_thong_bao': '19/10/2026', 'ly_do': reason,
            'sha256': 'abc', 'size': 10, 'reference_status': 'LEGACY_UNVERIFIED'}


def row(case: str, notices: list[dict], **extra) -> dict:
    base = {'ma_ho_so': case, 'nguon': 'DVC', 'to_khai': '01/GTGT',
            'ky_tinh_thue': 'Quý 3/2026', 'ngay_nop': '20/10/2026', 'lan_nop': '',
            '_file_status': 'downloaded', '_integrity_label': 'Chưa xác minh tham chiếu',
            '_notice_state': '', '_cqt_status': 'unknown', '_cqt_status_label': 'Chưa xác định',
            '_notices': notices}
    base.update(extra)
    return base


class ReconciliationRowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(cleanup_temporary_directory, self.temp)
        self.root = Path(self.temp.name)

    def test_one_row_per_feedback_and_empty_state(self):
        accept = self.root / 'accept.xml'
        reject = self.root / 'reject.xml'
        accept.write_bytes(b'<x/>')
        reject.write_bytes(b'<x/>')
        rows = [
            row('A', [notice(accept, state='accepted', kind='chap-nhan', number='1/TB'),
                      notice(reject, state='received', kind='tiep-nhan', number='2/TB')],
                _cqt_status='accepted', _cqt_status_label='Đã chấp nhận'),
            row('B', [notice(reject, state='rejected', kind='khong-chap-nhan', number='3/TB',
                             reason='Sai chỉ tiêu')],
                _cqt_status='rejected', _cqt_status_label='Không chấp nhận'),
            row('C', [], _cqt_status='none', _cqt_status_label=''),
            row('D', [{'path': str(self.root / 'missing.xml'), 'name': 'missing.xml',
                       'kind': 'khac', 'state': '', 'read_status': 'UNREADABLE',
                       'relative_path': 'thong-bao-dinh-kem/case/missing.xml',
                       'so_thong_bao': '', 'ngay_thong_bao': '', 'ly_do': '', 'sha256': '', 'size': 0}],
                _cqt_status='unknown', _cqt_status_label='Chưa xác định'),
        ]
        records = reconciliation_rows(rows, taxpayer_key='mst-A', scope_note='Phạm vi test')
        self.assertEqual(len(records), 5)
        by_case = {}
        for record in records:
            by_case.setdefault(record['ma_ho_so'], []).append(record)
        self.assertEqual(len(by_case['A']), 2)
        self.assertEqual({item['feedback_result'] for item in by_case['A']},
                         {'✓ Đã chấp nhận', '• Đã tiếp nhận'})
        self.assertEqual(by_case['B'][0]['feedback_result'], '✕ Không chấp nhận')
        self.assertEqual(by_case['B'][0]['cqt_status'], 'Không chấp nhận')
        self.assertEqual(by_case['C'][0]['feedback_result'], 'Chưa có phản hồi trong dữ liệu hiện có')
        self.assertEqual(by_case['C'][0]['asset_exists'], '—')
        self.assertEqual(by_case['D'][0]['feedback_result'], '? Chưa xác định')
        self.assertEqual(by_case['D'][0]['asset_exists'], 'Thiếu')
        self.assertTrue(all(item['pham_vi'] == 'Phạm vi test' for item in records))

    def test_csv_is_utf8_bom_and_blocks_formula_injection(self):
        path = self.root / 'doi-soat.csv'
        records = reconciliation_rows([
            row('A', [], to_khai='+SUM(1)', _cqt_status_label='@cmd'),
        ], scope_note='Phạm vi Unicode: Tờ khai')
        records[0]['feedback_number'] = '=HYPERLINK("x")'
        write_reconciliation_csv(path, records)
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        with path.open(encoding='utf-8-sig', newline='') as stream:
            parsed = list(csv.DictReader(stream))
        self.assertEqual(len(parsed), 1)
        self.assertTrue(parsed[0]['feedback_number'].startswith("'="))
        self.assertTrue(parsed[0]['to_khai'].startswith("'+"))
        self.assertTrue(parsed[0]['cqt_status'].startswith("'@"))
        self.assertIn('Phạm vi Unicode', parsed[0]['pham_vi'])

    def test_xlsx_has_scope_sheet_and_rejected_highlight(self):
        from openpyxl import load_workbook
        rejected = self.root / 'reject.xml'
        rejected.write_bytes(b'<x/>')
        records = reconciliation_rows([
            row('B', [notice(rejected, state='rejected', kind='khong-chap-nhan', number='=9/TB')],
                _cqt_status='rejected', _cqt_status_label='Không chấp nhận'),
        ], scope_note='Phạm vi XLSX')
        path = self.root / 'doi-soat.xlsx'
        write_reconciliation_xlsx(path, records, 'Phạm vi XLSX')
        workbook = load_workbook(path)
        self.addCleanup(workbook.close)
        self.assertIn('Đối soát', workbook.sheetnames)
        self.assertIn('Phạm vi', workbook.sheetnames)
        sheet = workbook['Đối soát']
        headers = [cell.value for cell in sheet[1]]
        self.assertIn('Kết quả phản hồi', headers)
        result_column = headers.index('Kết quả phản hồi') + 1
        self.assertTrue(str(sheet.cell(2, result_column).value).startswith('✕'))
        self.assertEqual(sheet.cell(2, 1).fill.fgColor.rgb[-6:].upper(), 'FDECEA')
        number_column = headers.index('Số thông báo') + 1
        self.assertEqual(sheet.cell(2, number_column).data_type, 's')
        self.assertTrue(str(sheet.cell(2, number_column).value).startswith("'="))
        scope = workbook['Phạm vi']
        self.assertEqual(scope.cell(1, 2).value, 'Phạm vi XLSX')


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class FilteredRowsTests(unittest.TestCase):
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

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    def test_filtered_rows_and_scope_note_follow_active_filters(self):
        from desktop.services import JobResult
        rows = [row('A', [], _cqt_status='accepted', _cqt_status_label='Đã chấp nhận'),
                row('B', [], _cqt_status='rejected', _cqt_status_label='Không chấp nhận')]
        self.window.result = JobResult('SUCCESS', 'x', self.root, rows=rows,
                                       date_range=('01/06/2025', '30/06/2025'))
        self.window.model.reset('tax', rows)
        self.window.search.setText('B')
        filtered = self.window.filtered_rows()
        self.assertEqual([item['ma_ho_so'] for item in filtered], ['B'])
        scope = self.window.reconciliation_scope()
        self.assertIn('Ngày nộp 01/06/2025 – 30/06/2025', scope)
        self.assertIn('Tìm kiếm "B"', scope)
        self.assertIn('không xác nhận đầy đủ nghĩa vụ thuế', scope)


if __name__ == '__main__':
    unittest.main()
