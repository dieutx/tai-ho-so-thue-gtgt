"""Notice states and references must survive corrupt files and ID collisions."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from desktop.notices import notice_state, read_notices


def xml(title='Chấp nhận hồ sơ', status='Y', reason=''):
    return (f'<TBaoThueDTu><TBaoThue><TTinTBaoThue><tenTBao>{title}</tenTBao>'
            '<soTBao>123/TB</soTBao></TTinTBaoThue><NDungTBao>'
            f'<trangThai>{status}</trangThai>{reason}</NDungTBao></TBaoThue></TBaoThueDTu>').encode()


class NoticeReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'thong-bao-dinh-kem' / 'case'
        self.folder.mkdir(parents=True)

    def save(self, name, data, parent=None):
        path = self.folder / name
        path.write_bytes(data)
        if parent is not None:
            info = {'source': {'parent_remote_id': 'case', 'parent_record_key': parent,
                               'record_key': 'attachment-' + parent},
                    'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'status': 'OK'}
            path.with_name(path.name + '.integrity.json').write_text(json.dumps(info), encoding='utf-8')
        return path

    def test_unknown_status_and_corrupt_xml_never_become_accepted(self):
        self.save('chap-nhan.xml', xml(status='NEW_STATUS'))
        self.save('xac-nhan.xml', b'<broken>')
        self.assertEqual(notice_state(read_notices(self.root, 'case')), '')
        self.assertEqual(len(read_notices(self.root, 'case')), 2)

    def test_nested_rejection_reason_is_read_and_overrides_generic_title(self):
        self.save('combined.xml', xml(title='Chấp nhận/Không chấp nhận hồ sơ',
                                    reason='<LyDo><CTietLyDo><tenLoi>Sai chỉ tiêu</tenLoi></CTietLyDo></LyDo>'))
        notices = read_notices(self.root, 'case')
        self.assertEqual(notices[0]['ly_do'], 'Sai chỉ tiêu')
        self.assertEqual(notice_state(notices), 'rejected')

    def test_reference_filters_same_remote_id_from_other_account_or_source(self):
        self.save('first.xml', xml(), 'account-source-A')
        self.save('second.xml', xml(title='Không chấp nhận hồ sơ', status='N'), 'account-source-B')
        notices = read_notices(self.root, 'case', parent_key='account-source-A')
        self.assertEqual(len(notices), 1)
        self.assertEqual(notice_state(notices), 'accepted')
        self.assertEqual(notices[0]['reference_key'], 'attachment-account-source-A')
        self.assertEqual(notices[0]['relative_path'], 'thong-bao-dinh-kem/case/first.xml')

    def test_changed_file_and_legacy_unowned_file_do_not_claim_verified_acceptance(self):
        changed = self.save('first.xml', xml(), 'parent')
        changed.write_bytes(xml(status='N'))
        self.save('legacy.xml', xml())
        notices = read_notices(self.root, 'case', parent_key='parent')
        self.assertEqual(notice_state(notices), '')
        self.assertEqual({item['reference_status'] for item in notices}, {'INVALID', 'LEGACY_UNVERIFIED'})

    def test_non_xml_files_remain_openable_and_empty_id_cannot_scan_parent(self):
        self.save('notice.pdf', b'%PDF-1.4\nfixture')
        self.save('notice.zip', b'PK\x03\x04fixture')
        self.assertEqual(len(read_notices(self.root, 'case')), 2)
        self.assertEqual(notice_state(read_notices(self.root, 'case')), '')
        self.assertEqual(read_notices(self.root, ''), [])

    def test_notice_export_keeps_parent_reference_and_literal_reason(self):
        from openpyxl import Workbook

        from desktop.notice_reports import notice_report_sheet
        from gdt_tax.run_hooks import RunHooks
        self.save('first.xml', xml(), 'parent')
        notices = read_notices(self.root, 'case', parent_key='parent')
        notices[0]['ly_do'] = '=HYPERLINK("untrusted")'
        sheet = notice_report_sheet(Workbook(), [{'ma_ho_so': 'case', 'record_key': 'parent', '_notices': notices}], RunHooks())
        self.assertEqual(sheet.cell(2, 3).value, 'parent')
        self.assertEqual(sheet.cell(2, 8).data_type, 's')
        self.assertEqual(sheet.cell(2, 9).value, 'thong-bao-dinh-kem/case/first.xml')
        self.assertEqual(sheet.cell(2, 10).value, 'attachment-parent')

    def test_full_export_includes_local_notice_state_and_reference_sheet(self):
        from openpyxl import load_workbook

        from desktop.reports import export_document_report
        from desktop.services import RunConfig
        from gdt_tax.constants import SOURCE_ETAX_LEGACY
        from gdt_tax.models import CaseRecord
        from gdt_tax.run_hooks import RunHooks
        self.save('first.xml', xml())
        config = RunConfig('tax', self.root, source=self.root, action='export_report',
                           input_rows=[CaseRecord('case', SOURCE_ETAX_LEGACY).to_dict()],
                           report_path=self.root / 'report.xlsx')
        export_document_report(config, RunHooks())
        workbook = load_workbook(config.report_path)
        self.addCleanup(workbook.close)
        sheet = workbook['Danh sách hồ sơ']
        headers = [cell.value for cell in sheet[1]]
        self.assertEqual(sheet.cell(2, headers.index('Thông báo cơ quan thuế') + 1).value, 'Chấp nhận')
        self.assertEqual(workbook['Thông báo tờ khai'].cell(2, 9).value, 'thong-bao-dinh-kem/case/first.xml')

    def test_scoped_rows_use_notice_store_parent_identity_instead_of_folder_name_only(self):
        try:
            from gdt_tax.identity import account_fingerprint
        except ImportError:
            self.skipTest('Scoped core identity is available in the integration checkout')
        from desktop.documents import verify_rows
        from gdt_tax.dvc_notices import DvcNotice, NoticeFile, NoticeStore
        from gdt_tax.models import CaseRecord
        records = [CaseRecord('case', source, account_key=account_fingerprint(account))
                   for account, source in [('account-A', 'DVC'), ('account-A', 'ETAX_LEGACY'), ('account-B', 'DVC')]]
        store = NoticeStore(self.root / 'thong-bao-dinh-kem')
        for index, record in enumerate(records):
            notice = DvcNotice('notice-' + str(index), title='Chấp nhận hồ sơ' if index == 0 else 'Không chấp nhận hồ sơ')
            path = store.save(record.key, notice, NoticeFile('notice.xml', xml(title=notice.title, status='Y' if index == 0 else 'N')))
            self.assertIsNotNone(path)
        row = verify_rows('tax', [records[0].to_dict()], self.root)[0]
        self.assertEqual(row['_notice_state'], 'accepted')
        self.assertEqual(len(row['_notices']), 1)
        self.assertEqual(row['_notices'][0]['parent_key'], records[0].record_key)


if __name__ == '__main__':
    unittest.main()
