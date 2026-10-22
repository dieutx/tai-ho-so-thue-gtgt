"""v2 acceptance: real date ordering, independent states and targeted writes."""
from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import logging
import os
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from desktop.documents import (
    amount_value,
    counters,
    display_amount,
    document_id,
    event_datetime,
    record_from_row,
    remote_document_id,
    verify_rows,
)
from desktop.services import JobResult, RunConfig, run_offline, run_online
from desktop.settings_store import Preferences, SettingsStore
from gdt_tax.constants import SOURCE_ETAX_LEGACY
from gdt_tax.errors import NetworkError, StorageError
from gdt_tax.gnt.models import GiayNopTien
from gdt_tax.gnt.storage import GntStore
from gdt_tax.identity import RecordKey, account_fingerprint
from gdt_tax.integrity import source_reference, validate_tax_zip, write_evidence
from gdt_tax.models import CaseRecord
from gdt_tax.run_hooks import RunHooks
from gdt_tax.storage import ZipStore
from tests.support import FakeHttp, StubCaptcha, cleanup_temporary_directory, sample_zip
from tests.test_etax_legacy import make_legacy_handler
from tests.test_gnt import make_gnt_handler
from tests.test_tb import make_tb_handler

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None


def notice_xml(title: str, so: str, *, ly_do: str = '', ngay: str = '2026-09-11') -> str:
    reason = f'<LyDo>{ly_do}</LyDo>' if ly_do else ''
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<TBaoThueDTu xmlns="http://kekhaithue.gdt.gov.vn/TBaoThue"><TBaoThue>'
            f'<TTinTBaoThue><maTBao>844</maTBao><tenTBao>{title}</tenTBao>'
            f'<soTBao>{so}</soTBao><ngayTBao>{ngay}</ngayTBao></TTinTBaoThue>'
            f'<NDungTBao><trangThai>Y</trangThai>{reason}</NDungTBao>'
            '</TBaoThue></TBaoThueDTu>')


class DocumentStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.prefs = Preferences(record_delay=0, page_delay=0, jitter=0, login_attempts=1, search_attempts=1)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def test_dates_and_amounts_do_not_sort_display_strings_or_round(self):
        dates = ['21/09/2026 18:07', '30/09/2026 08:00', '20/08/2026 23:59']
        self.assertEqual(sorted(dates, key=event_datetime, reverse=True), [dates[1], dates[0], dates[2]])
        self.assertEqual(amount_value('844.526.143'), Decimal('844526143'))
        self.assertEqual(display_amount('844.526.143'), '844.526.143 ₫')
        self.assertEqual(display_amount('-1.234,56'), '-1.234,56 ₫')
        self.assertEqual(display_amount(0), '0 ₫')
        self.assertIsNone(amount_value('NULL'))
        self.assertIsNone(amount_value('1e3'))

    def test_tax_rejection_and_local_zip_are_independent(self):
        record = CaseRecord('fixture-rejected', SOURCE_ETAX_LEGACY, trang_thai='Không chấp nhận')
        ZipStore(self.root).save(record, sample_zip())
        row = verify_rows('tax', [record.to_dict()], self.root)[0]
        self.assertEqual(row['trang_thai'], 'Không chấp nhận')
        self.assertEqual(row['_file_status'], 'downloaded')
        self.assertTrue(row['_needs_review'])
        self.assertEqual(counters([row])['failed'], 0)

    def test_gnt_rejected_approval_is_review_not_download_error(self):
        row = GiayNopTien('fixture-gnt', trang_thai='Bị từ chối phê duyệt').to_dict()
        result = verify_rows('gnt', [row], self.root)[0]
        self.assertTrue(result['_needs_review'])
        self.assertEqual(counters([result]), {'found': 1, 'downloaded': 0, 'failed': 0, 'pending': 1})

    def test_tax_notice_xml_marks_rejection_and_lists_files(self):
        case = 'fixture-case'
        folder = self.root / 'thong-bao-dinh-kem' / case
        folder.mkdir(parents=True)
        (folder / f'112__tiep-nhan__{case}__Tiep-nhan-ho-so.xml').write_text(
            notice_xml('V/v: Tiếp nhận hồ sơ thuế điện tử', '1109094948983/2026'), encoding='utf-8')
        rejected = folder / f'113__khong-chap-nhan__{case}__Khong-chap-nhan-ho-so.xml'
        rejected.write_text(notice_xml('V/v: Không chấp nhận hồ sơ khai thuế',
                                       '298018/0109/2026/TB-TĐT', ly_do='Hồ sơ không hợp lệ'), encoding='utf-8')
        row = verify_rows('tax', [CaseRecord(case, SOURCE_ETAX_LEGACY).to_dict()], self.root)[0]
        self.assertEqual(row['_notice_state'], 'rejected')
        self.assertEqual(row['_notice_summary'], 'Không chấp nhận (2)')
        self.assertTrue(row['_needs_review'])
        self.assertEqual([item['kind'] for item in row['_notices']], ['tiep-nhan', 'khong-chap-nhan'])
        self.assertEqual(row['_notices'][1]['so_thong_bao'], '298018/0109/2026/TB-TĐT')
        self.assertEqual(row['_notices'][1]['ly_do'], 'Hồ sơ không hợp lệ')

    def test_tax_notice_legacy_combined_title_without_reason_is_accepted(self):
        case = 'fixture-legacy-ok'
        folder = self.root / 'thong-bao-dinh-kem' / case
        folder.mkdir(parents=True)
        (folder / f'901__khac__{case}__Chap-nhan-Khong-chap-nhan-ve-viec-nop-ho-so.xml').write_text(
            notice_xml('V/v: Chấp nhận/Không chấp nhận về việc nộp hồ sơ', '0120145518684/2020'),
            encoding='utf-8')
        row = verify_rows('tax', [CaseRecord(case, SOURCE_ETAX_LEGACY).to_dict()], self.root)[0]
        self.assertEqual(row['_notice_state'], 'accepted')
        self.assertFalse(row['_needs_review'])

    def test_tax_notice_legacy_ambiguous_title_reads_reason(self):
        case = 'fixture-legacy'
        folder = self.root / 'thong-bao-dinh-kem' / case
        folder.mkdir(parents=True)
        (folder / f'900__khac__{case}__Chap-nhan-Khong-chap-nhan-ve-viec-nop-ho-so.xml').write_text(
            notice_xml('V/v: Chấp nhận/Không chấp nhận về việc nộp hồ sơ', '123/TB', ly_do='Sai mẫu tờ khai'),
            encoding='utf-8')
        row = verify_rows('tax', [CaseRecord(case, SOURCE_ETAX_LEGACY).to_dict()], self.root)[0]
        self.assertEqual(row['_notice_state'], 'rejected')
        self.assertEqual(row['_notice_summary'], 'Không chấp nhận')

    def test_tax_accepted_notice_is_not_flagged_for_review(self):
        case = 'fixture-accepted'
        folder = self.root / 'thong-bao-dinh-kem' / case
        folder.mkdir(parents=True)
        (folder / f'112__tiep-nhan__{case}__Tiep-nhan.xml').write_text(
            notice_xml('V/v: Tiếp nhận hồ sơ thuế điện tử', '1109094948983/2026'), encoding='utf-8')
        (folder / f'113__chap-nhan__{case}__Xac-nhan-nop-ho-so.xml').write_text(
            notice_xml('V/v: Xác nhận nộp hồ sơ thuế điện tử', '298018/0109/2026/TB-TĐT'), encoding='utf-8')
        row = verify_rows('tax', [CaseRecord(case, SOURCE_ETAX_LEGACY).to_dict()], self.root)[0]
        self.assertEqual(row['_notice_state'], 'accepted')
        self.assertEqual(row['_notice_summary'], 'Chấp nhận (2)')
        self.assertFalse(row['_needs_review'])

    def test_notice_seen_without_pdf_is_not_downloaded(self):
        row = verify_rows('notice', [{'message_id': 'fixture-notice', 'trang_thai': 'Đã xem'}], self.root)[0]
        self.assertEqual(row['_file_status'], 'not_downloaded')
        self.assertEqual(row['trang_thai'], 'Đã xem')

    def test_deleted_file_is_detected_and_query_verification_never_renames(self):
        record = CaseRecord('fixture-old', SOURCE_ETAX_LEGACY)
        original = self.root / 'fixture-old-oldname.zip'
        original.write_bytes(sample_zip())
        first = verify_rows('tax', [record.to_dict()], self.root)[0]
        self.assertTrue(original.is_file())
        self.assertEqual(first['_file_status'], 'downloaded')
        original.unlink()
        second = verify_rows('tax', [first], self.root)[0]
        self.assertEqual(second['_file_status'], 'not_downloaded')
        self.assertIn('xóa/di chuyển', second['_file_reason'])

    def test_gui_query_writes_no_catalog_or_attachment_for_all_portals(self):
        for mode, factory in [('tax', make_legacy_handler), ('gnt', make_gnt_handler), ('notice', make_tb_handler)]:
            with self.subTest(mode=mode):
                output = self.root / mode
                config = RunConfig(mode, output, username='fixture-user', password='fixture-secret', preferences=self.prefs, dry_run=True)
                config.validate()
                result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'), http=FakeHttp(factory({})))
                self.assertEqual(result.state, 'SUCCESS', result.message)
                self.assertFalse(output.exists())
                self.assertEqual(result.files, [])
                self.assertTrue(all(row['_file_status'] == 'not_downloaded' for row in result.rows))

    def test_selected_download_writes_only_requested_attachments_for_all_portals(self):
        for mode, factory, suffix in [('tax', make_legacy_handler, '.zip'), ('gnt', make_gnt_handler, '.xml'), ('notice', make_tb_handler, '.pdf')]:
            with self.subTest(mode=mode):
                config = RunConfig(mode, self.root / mode, username='fixture-user', password='fixture-secret', preferences=self.prefs, dry_run=True)
                query = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'), http=FakeHttp(factory({})))
                selected = query.rows[-1]
                key = document_id(mode, selected)
                download = replace(config, dry_run=False, action='download_selected', target_ids=(key,), input_rows=[selected])
                download.validate()
                result = run_online(download, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'), http=FakeHttp(factory({})))
                self.assertEqual(result.state, 'SUCCESS', result.message)
                self.assertEqual(result.downloaded, 1)
                self.assertEqual(len(list(config.output.glob('*' + suffix))), 1)
                self.assertEqual([document_id(mode, r) for r in result.rows if r['_file_status'] == 'downloaded'], [key])

    def test_existing_valid_xml_survives_selected_retry_without_content_change(self):
        from gdt_tax.ownership import check_owner
        check_owner(self.root, account_fingerprint('fixture-user'), create=True)
        config = RunConfig('gnt', self.root, username='fixture-user', password='fixture-secret', preferences=self.prefs)
        query = run_online(replace(config, dry_run=True), RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'), http=FakeHttp(make_gnt_handler({})))
        row = query.rows[0]
        record = record_from_row('gnt', row)
        path = GntStore(self.root).save(record, Path('tests/fixtures/gnt_chungtu.xml').read_bytes())
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        state = {}
        result = run_online(replace(config, target_ids=(record.ctu_id,), input_rows=[row]), RunHooks(), StubCaptcha(),
                            logging.getLogger('gdt_tax.test'), http=FakeHttp(make_gnt_handler(state)))
        self.assertEqual(result.reused, 1)
        self.assertFalse(state.get('downloads'))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_explicit_xml_selection_does_not_scan_other_files_or_upload(self):
        source = self.root / 'source'
        source.mkdir()
        selected = source / 'selected.xml'
        selected.write_bytes(Path('tests/fixtures/gnt_chungtu.xml').read_bytes())
        (source / 'unselected.xml').write_text('<unselected/>')
        config = RunConfig('offline', self.root / 'output', source=source, source_files=(str(selected),))
        config.validate()
        with patch('socket.socket.connect', side_effect=AssertionError('XML uploaded')):
            result = run_offline(config, RunHooks(), logging.getLogger('gdt_tax.test'))
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(selected.read_bytes(), Path('tests/fixtures/gnt_chungtu.xml').read_bytes())

    def test_selected_network_failure_is_attached_to_one_record_and_queue_continues(self):
        state = {}
        handler = make_gnt_handler(state)
        def failing_one(method, path, kwargs):
            data = kwargs.get('data') or {}
            if data.get('dse_nextEventName') == 'download' and data.get('ctuId') == '900000001':
                raise NetworkError('HTTP 500 sau các lần retry hữu hạn')
            return handler(method, path, kwargs)
        config = RunConfig('gnt', self.root, username='fixture-user', password='fixture-secret', preferences=self.prefs,
                           target_ids=('900000001', '900000002'), action='download_selected')
        result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'), http=FakeHttp(failing_one))
        self.assertEqual(result.state, 'PARTIAL')
        self.assertEqual(result.errors, 1)
        self.assertEqual(state['downloads'], ['900000002'])
        self.assertEqual(RecordKey.parse(result.issues[0]['document_id']).remote_id, '900000001')
        self.assertIn('HTTP 500', result.issues[0]['message'])

    def test_primary_completion_does_not_hide_failed_tax_notices(self):
        from tests.support import FakeResponse, route_of
        from tests.test_dvc_notices import DETAIL_HTML
        from tests.test_pipeline import dvc_search, make_handler
        base = make_handler(search=dvc_search)

        def handler(method, path, kwargs):
            route = route_of(path)
            if route.startswith('/tchs/files/detail/'):
                return FakeResponse(DETAIL_HTML)
            if route == '/tchs/downloadthongbao':
                return FakeResponse(status_code=429)
            return base(method, path, kwargs)

        config = RunConfig('tax', self.root, username='fixture-user', password='fixture-secret',
                           preferences=self.prefs, dvc=True, from_date='01/01/2026', to_date='31/01/2026')
        result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'), http=FakeHttp(handler))
        self.assertEqual(result.state, 'PARTIAL', result.message)
        self.assertEqual(result.downloaded, 2)
        self.assertEqual(result.errors, 0)
        self.assertIn('thông báo cơ quan thuế chưa đầy đủ', result.message)
        self.assertEqual(len(result.issues), 2)
        self.assertTrue(all('HTTP 429' in issue['message'] for issue in result.issues))

    def test_gui_resume_keeps_original_zip_filename(self):
        from gdt_tax.ownership import check_owner
        check_owner(self.root, account_fingerprint('fixture-user'), create=True)
        config = RunConfig('tax', self.root, username='fixture-user', password='fixture-secret', preferences=self.prefs, dry_run=True)
        query = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'), http=FakeHttp(make_legacy_handler({})))
        row = query.rows[0]
        key = document_id('tax', row)
        original = self.root / (remote_document_id('tax', row) + '-legacy.zip')
        original.write_bytes(sample_zip())
        write_evidence(original, validate_tax_zip(sample_zip()), source_reference(record_from_row('tax', row), 'zip'))
        result = run_online(replace(config, dry_run=False, target_ids=(key,), input_rows=[row]), RunHooks(), StubCaptcha(),
                            logging.getLogger('gdt_tax.test'), http=FakeHttp(make_legacy_handler({})))
        self.assertEqual(result.reused, 1)
        self.assertTrue(original.is_file())
        self.assertEqual(list(self.root.glob('*.zip')), [original])

    def test_explicit_report_export_needs_no_network_or_credentials_and_escapes_formula(self):
        from openpyxl import load_workbook

        from desktop.reports import export_document_report
        row = CaseRecord('fixture-report', SOURCE_ETAX_LEGACY, to_khai='=HYPERLINK("bad")', trang_thai='Không chấp nhận').to_dict()
        config = RunConfig('tax', self.root, source=self.root, action='export_report', input_rows=[row], report_path=self.root / 'report.xlsx')
        config.validate()
        with patch('socket.socket.connect', side_effect=AssertionError('report used network')):
            result = export_document_report(config, RunHooks())
        self.assertEqual(result.state, 'SUCCESS')
        workbook = load_workbook(result.files[0], data_only=False)
        self.assertEqual(workbook.worksheets[0].cell(2, 2).data_type, 's')
        headings = [cell.value for cell in workbook.worksheets[0][1]]
        self.assertEqual(workbook.worksheets[0].cell(2, headings.index('Trạng thái tệp') + 1).value, 'Chưa tải')
        workbook.close()

    def test_refresh_keeps_last_download_error_until_file_is_valid(self):
        row = {'message_id': 'fixture-failed', '_file_status': 'failed', '_error_message': 'HTTP 500'}
        refreshed = verify_rows('notice', [row], self.root)[0]
        self.assertEqual(refreshed['_file_status'], 'failed')
        self.assertEqual(refreshed['_error_message'], 'HTTP 500')

    def test_disk_full_catalog_error_preserves_files_without_false_file_failures(self):
        from desktop.services import ONLINE
        error = StorageError('cannot commit catalog')
        error.__cause__ = OSError(errno.ENOSPC, 'disk full')
        kind, _, report = ONLINE['gnt']
        config = RunConfig('gnt', self.root, username='fixture', password='fixture', preferences=self.prefs)
        with patch.dict(ONLINE, {'gnt': (kind, Mock(side_effect=error), report)}):
            result = run_online(config, RunHooks(), StubCaptcha(), logging.getLogger('gdt_tax.test'), http=FakeHttp(make_gnt_handler({})))
        self.assertEqual(result.state, 'ERROR')
        self.assertIn('ổ đĩa đã hết dung lượng', result.message)
        self.assertEqual(counters(result.rows)['failed'], 0)
        self.assertGreater(result.downloaded, 0)
        self.assertEqual(result.files, [])


@unittest.skipUnless(HAS_QT, 'Optional desktop Qt dependencies')
class DesktopV2InteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.ui import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = MainWindow(SettingsStore(self.root / 'settings.json'))

    def tearDown(self):
        self.window.close()
        cleanup_temporary_directory(self.temp)

    def test_proxy_sorts_timestamp_descending_and_review_does_not_mean_failed(self):
        from PySide6.QtCore import Qt
        rows = [dict(CaseRecord(str(i), SOURCE_ETAX_LEGACY, ngay_nop=day, trang_thai='Không chấp nhận').to_dict(), _file_status='not_downloaded')
                for i, day in enumerate(['21/09/2026', '30/09/2026', '20/08/2026'])]
        self.window.model.reset('tax', rows)
        self.window.proxy_model.sort(3, Qt.SortOrder.DescendingOrder)
        self.assertEqual(self.window.proxy_model.index(0, 3).data(), '30/09/2026')
        self.window.proxy_model.set_status_filter('failed')
        self.assertEqual(self.window.proxy_model.rowCount(), 0)
        self.window.proxy_model.set_status_filter('review')
        self.assertEqual(self.window.proxy_model.rowCount(), 3)

    def test_select_visible_rows_and_download_uses_original_query_period(self):
        rows = [dict(CaseRecord(str(i), SOURCE_ETAX_LEGACY, to_khai=title, account_key=account_fingerprint('fixture-user')).to_dict(), _file_status='not_downloaded')
                for i, title in enumerate(['Match one', 'Match two', 'Other'])]
        self.window.controller.sessions.set_account('fixture-user', 'fixture-secret')
        self.window.result = JobResult('SUCCESS', 'Query', self.root, rows=rows, date_range=('01/06/2025', '30/06/2025'),
                                      account_key=hashlib.sha256(b'fixture-user').hexdigest(), operation='query')
        self.window.model.reset('tax', rows)
        self.window.search.setText('Match')
        self.window.select_visible_header(0)
        with patch.object(self.window, 'launch') as launch:
            self.window.download_checked()
        config = launch.call_args.args[0]
        self.assertEqual(set(config.target_ids), {document_id('tax', row) for row in rows[:2]})
        self.assertEqual(config.from_date, '01/06/2025')
        self.assertEqual(config.output, self.root)

    def test_rejected_notice_column_shows_red_warning(self):
        from PySide6.QtCore import Qt

        from desktop.table_model import COLUMNS
        column = next(index for index, (key, _) in enumerate(COLUMNS['tax']) if key == '_notice_state')
        row = dict(CaseRecord('fixture', SOURCE_ETAX_LEGACY, trang_thai='Đã chấp nhận').to_dict(),
                   _notice_state='rejected', _notice_summary='Không chấp nhận (2)',
                   _notices=[{'kind_label': 'Tiếp nhận', 'so_thong_bao': '1109094948983/2026', 'name': 'tiep-nhan.xml'},
                             {'kind_label': 'Không chấp nhận', 'so_thong_bao': '298018/0109/2026/TB-TĐT',
                              'ly_do': 'Hồ sơ không hợp lệ', 'name': 'khong-chap-nhan.xml'}])
        self.window.model.reset('tax', [row])
        index = self.window.model.index(0, column)
        self.assertEqual(index.data(), 'Xem phản hồi (2)')
        self.assertIn('Bấm để xem phản hồi', index.data(Qt.ItemDataRole.ToolTipRole))
        self.assertIn('298018/0109/2026/TB-TĐT', index.data(Qt.ItemDataRole.ToolTipRole))
        self.assertTrue(index.data(Qt.ItemDataRole.FontRole).underline())
        self.assertEqual(index.data(Qt.ItemDataRole.BackgroundRole).name(), '#fdecea')
        self.assertEqual(index.data(Qt.ItemDataRole.ForegroundRole).name(), '#225de9')
        status_column = next(index for index, (key, _) in enumerate(COLUMNS['tax']) if key == 'trang_thai')
        self.assertEqual(self.window.model.index(0, status_column).data(), 'Không chấp nhận')
        accepted = dict(row, _notice_state='accepted', _notice_summary='Chấp nhận (2)')
        self.window.model.reset('tax', [accepted])
        self.assertIsNone(self.window.model.index(0, column).data(Qt.ItemDataRole.BackgroundRole))

    def test_notice_rejection_is_searchable_and_in_review_filter(self):
        from desktop.table_model import COLUMNS
        row = dict(CaseRecord('fixture', SOURCE_ETAX_LEGACY, trang_thai='Đã chấp nhận').to_dict(),
                   _notice_state='rejected', _notices=[{'so_thong_bao': '123/TB', 'ly_do': 'Sai chỉ tiêu'}])
        self.window.model.reset('tax', [row])
        self.window.proxy_model.set_status_filter('review')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.proxy_model.setFilterFixedString('123/TB')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.proxy_model.setFilterFixedString('Sai chỉ tiêu')
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.proxy_model.set_status_filter('all')
        self.window.proxy_model.setFilterFixedString('')
        self.window.model.reset('tax', [dict(row, _notice_state='')])
        column = next(i for i, (key, _) in enumerate(COLUMNS['tax']) if key == '_notice_state')
        self.assertEqual(self.window.model.index(0, column).data(), 'Xem phản hồi (1)')

    def test_notice_menu_lists_and_opens_downloaded_xml(self):
        from desktop.table_model import COLUMNS
        target = self.root / 'thong-bao-dinh-kem' / 'fixture'
        target.mkdir(parents=True)
        notice = target / '113__khong-chap-nhan__fixture__Khong-chap-nhan.xml'
        notice.write_text(notice_xml('V/v: Không chấp nhận hồ sơ', '298018/0109/2026/TB-TĐT'), encoding='utf-8')
        column = next(index for index, (key, _) in enumerate(COLUMNS['tax']) if key == '_notice_state')
        row = verify_rows('tax', [CaseRecord('fixture', SOURCE_ETAX_LEGACY).to_dict()], self.root)[0]
        self.window.model.reset('tax', [row])
        self.window.table.setCurrentIndex(self.window.proxy_model.index(0, column))
        menu = self.window.notice_menu(row)
        self.assertEqual(menu.actions()[0].text(), 'Không chấp nhận · 298018/0109/2026/TB-TĐT')
        with patch.object(self.window, 'open_path') as opener:
            menu.actions()[0].trigger()
        opener.assert_called_once_with(notice)
        self.window.details()
        self.assertFalse(self.window.detail_notices.isHidden())
        self.assertTrue(self.window.detail_notices.isEnabled())
        self.assertEqual(self.window.detail_notices.text(), 'Xem phản hồi (1)')
        self.assertIn('1 phản hồi', self.window.detail_text.toPlainText())
        self.window.show_feedback_panel(row)
        panel = self.window.feedback_panel
        self.assertEqual(panel.table.rowCount(), 1)
        with patch('desktop.xml_viewer.XmlViewer.show_asset') as opener:
            panel.open_asset.emit(panel.items[0])
        opener.assert_called_once()
        with patch.object(self.window, 'open_path') as opener:
            self.window.open_notice(row['_notices'][0])
        opener.assert_called_once_with(notice)
        with patch.object(self.window, 'open_path') as opener:
            self.window.open_notice(row['_notices'][0], folder=True)
        opener.assert_called_once_with(notice.parent)
        notice.unlink()
        with patch.object(self.window, 'open_path') as opener, patch.object(self.window, 'error') as error:
            self.window.open_notice(row['_notices'][0])
        opener.assert_not_called()
        error.assert_called_once()

    def test_missing_attachments_are_visible_in_notice_column(self):
        from desktop.table_model import COLUMNS
        row = dict(CaseRecord('fixture', SOURCE_ETAX_LEGACY).to_dict(), attachment_result=json.dumps({
            'status': 'PARTIAL', 'discovered': 2, 'failed': 2, 'items': [{'code': 'ATTACHMENT_RATE_LIMITED'}]}))
        self.window.model.reset('tax', [row])
        column = next(i for i, (key, _) in enumerate(COLUMNS['tax']) if key == '_notice_state')
        self.assertEqual(self.window.model.index(0, column).data(), 'Chưa có phản hồi')
        from PySide6.QtCore import Qt
        self.assertIn('HTTP 429', self.window.model.index(0, column).data(Qt.ItemDataRole.ToolTipRole))
        self.assertEqual(self.window.model.index(0, column).data(Qt.ItemDataRole.ForegroundRole).name(), '#93631b')

    def test_stale_proxy_index_is_rejected_instead_of_crashing(self):
        rows = [CaseRecord(str(i), SOURCE_ETAX_LEGACY, to_khai=f'fixture {i}').to_dict() for i in range(4)]
        self.window.model.reset('tax', rows)
        stale = self.window.proxy_model.index(3, 1)
        self.window.model.reset('tax', rows[:1])
        self.assertIsNone(self.window.proxy_model.source_row(stale))
        self.assertEqual(self.window.proxy_model.source_row(self.window.proxy_model.index(0, 1)), 0)

    def test_unknown_or_other_account_rows_require_new_query(self):
        self.window.controller.sessions.set_account('fixture-user', 'fixture-secret')
        account = account_fingerprint('fixture-user')
        self.window.result = JobResult('SUCCESS', 'Query', self.root,
                                      date_range=('01/06/2025', '30/06/2025'),
                                      account_key=account, operation='query')
        for owner in ('UNKNOWN', account_fingerprint('another-user')):
            row = CaseRecord('same-id', SOURCE_ETAX_LEGACY, account_key=owner).to_dict()
            with self.subTest(owner=owner), patch.object(self.window, 'launch') as launch, \
                    patch.object(self.window, 'error') as error:
                self.window.download_rows([row])
                launch.assert_not_called()
                error.assert_called_once()

    def test_drawer_closes_without_changing_filter_or_scroll(self):
        row = CaseRecord('fixture', SOURCE_ETAX_LEGACY, to_khai='Tờ khai fixture').to_dict()
        self.window.model.reset('tax', [row])
        self.window.search.setText('fixture')
        self.window.table.setCurrentIndex(self.window.proxy_model.index(0, 1))
        self.window.details()
        self.assertFalse(self.window.drawer.isHidden())
        self.window.close_drawer()
        self.assertTrue(self.window.drawer.isHidden())
        self.assertEqual(self.window.search.text(), 'fixture')

    def test_selected_completion_preserves_unselected_query_rows(self):
        rows = [dict(CaseRecord(str(i), SOURCE_ETAX_LEGACY).to_dict(), _file_status='not_downloaded') for i in range(3)]
        self.window.controller.sessions.set_account('fixture-user', 'fixture-secret')
        account = hashlib.sha256(b'fixture-user').hexdigest()
        self.window.result = JobResult('SUCCESS', 'Query', self.root, rows=rows, date_range=('01/06/2025', '30/06/2025'),
                                      account_key=account, operation='query')
        self.window.model.reset('tax', rows)
        self.window.active_config = replace(self.window.make_config('tax'), target_ids=('0',), action='download_selected')
        completed = JobResult('SUCCESS', 'Done', self.root, rows=[dict(rows[0], _file_status='downloaded')],
                              downloaded=1, account_key=account, operation='download_selected', date_range=('01/06/2025', '30/06/2025'))
        self.window.on_completed(completed)
        self.assertEqual(len(self.window.model.rows), 3)
        self.assertEqual(self.window.model.rows[1]['_file_status'], 'not_downloaded')

    def test_keyboard_space_and_ctrl_a_operate_checkboxes(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        rows = [CaseRecord(str(i), SOURCE_ETAX_LEGACY).to_dict() for i in range(2)]
        self.window.model.reset('tax', rows)
        self.window.show()
        self.app.processEvents()
        self.window.table.setCurrentIndex(self.window.proxy_model.index(0, 1))
        self.window.table.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window.table, Qt.Key.Key_Space)
        self.assertEqual(len(self.window.model.checked), 1)
        QTest.keyClick(self.window.table, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.window.model.checked), 2)

    def test_account_clear_removes_drawer_and_old_query_summary(self):
        row = CaseRecord('previous-account-record', SOURCE_ETAX_LEGACY).to_dict()
        self.window.model.reset('tax', [row])
        self.window.table.setCurrentIndex(self.window.proxy_model.index(0, 1))
        self.window.details()
        self.window.collapse_conditions(True)
        self.window.clear_account_views()
        self.assertTrue(self.window.drawer.isHidden())
        self.assertTrue(self.window.condition_summary.isHidden())
        self.assertEqual(self.window.model.rowCount(), 0)
        self.assertIsNone(self.window.detail_row)

    def test_open_folder_actions_are_disabled_until_query_folder_exists(self):
        self.window.result = JobResult('SUCCESS', 'Query', self.root / 'not-created')
        self.window.populate_result(self.window.result)
        self.assertFalse(self.window.open_folder_button.isEnabled())
        self.assertFalse(self.window.folder_button.isEnabled())
        self.assertFalse(self.window.result.output.exists())
