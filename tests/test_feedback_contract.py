"""Hợp đồng S01: thực thể, khóa ổn định và trạng thái độc lập.

Fixtures F0–F11 theo MASTER_PLAN §7. Test dùng đúng ``read_notices`` để ánh xạ
từ XML thật, không dựng dict giả thay cho parser.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from desktop.domain import (
    BUSINESS_ACCEPTED,
    BUSINESS_NONE,
    BUSINESS_RECEIVED,
    BUSINESS_REJECTED,
    BUSINESS_UNKNOWN,
    DOWNLOAD_DOWNLOADED,
    DOWNLOAD_NOT_DOWNLOADED,
    INTEGRITY_INVALID,
    INTEGRITY_LABELS,
    INTEGRITY_UNVERIFIED,
    INTEGRITY_VERIFIED,
    OWNER_DECLARATION,
    OWNER_FEEDBACK,
    OWNER_TAX_NOTICE,
    aggregate_feedback_result,
    assets_from_row,
    business_status_from_text,
    declaration_asset,
    feedbacks_from_row,
    has_conflicting_results,
    submission_from_row,
    submission_key,
    tax_notice_asset,
    tax_notice_from_row,
    tax_notice_key,
)
from desktop.notices import read_notices
from gdt_tax.constants import SOURCE_DVC, SOURCE_TB
from gdt_tax.models import CaseRecord
from gdt_tax.tb.models import ThongBao


def notice_xml(title: str, *, status: str = 'Y', reason: str = '', number: str = '123/TB',
               issued: str = '2026-09-11', namespace: bool = False) -> bytes:
    ns = ' xmlns="http://kekhaithue.gdt.gov.vn/TBaoThue"' if namespace else ''
    reason_xml = f'<LyDo><CTietLyDo><tenLoi>{reason}</tenLoi></CTietLyDo></LyDo>' if reason else ''
    return (f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<TBaoThueDTu{ns}><TBaoThue><TTinTBaoThue><tenTBao>{title}</tenTBao>'
            f'<soTBao>{number}</soTBao><ngayTBao>{issued}</ngayTBao></TTinTBaoThue>'
            f'<NDungTBao><trangThai>{status}</trangThai>{reason_xml}</NDungTBao>'
            '</TBaoThue></TBaoThueDTu>').encode()


class ContractTestBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def save(self, case_id: str, name: str, data: bytes) -> Path:
        folder = self.root / 'thong-bao-dinh-kem' / case_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(data)
        return path

    def row(self, case_id: str = 'case-A', *, source: str = SOURCE_DVC, **extra) -> dict:
        record = CaseRecord(case_id, source, **{k: v for k, v in extra.items() if k in CaseRecord.__dataclass_fields__})
        row = record.to_dict()
        row.update({k: v for k, v in extra.items() if k.startswith('_')})
        key = case_id
        notices = read_notices(self.root, key)
        row.setdefault('_notices', notices)
        row.setdefault('_file_status', DOWNLOAD_NOT_DOWNLOADED)
        return row


class SubmissionStatusTests(ContractTestBase):
    def test_f0_no_feedback_is_none_not_accepted(self):
        row = self.row()
        submission = submission_from_row(row, taxpayer_key='mst-A')
        self.assertEqual(submission.tax_processing_status, BUSINESS_NONE)
        self.assertEqual(submission.download_status, DOWNLOAD_NOT_DOWNLOADED)

    def test_f1_single_received_is_received_not_accepted(self):
        self.save('case-A', 'tb3.xml', notice_xml('Tiếp nhận hồ sơ'))
        submission = submission_from_row(self.row(), taxpayer_key='mst-A')
        self.assertEqual(submission.tax_processing_status, BUSINESS_RECEIVED)

    def test_f2_received_and_accepted_aggregate_to_accepted(self):
        self.save('case-A', 'tb1.xml', notice_xml('Tiếp nhận hồ sơ'))
        self.save('case-A', 'tb2.xml', notice_xml('Chấp nhận hồ sơ'))
        feedbacks = feedbacks_from_row(self.row(), taxpayer_key='mst-A')
        self.assertEqual(len(feedbacks), 2)
        self.assertEqual(aggregate_feedback_result(feedbacks), BUSINESS_ACCEPTED)
        self.assertFalse(has_conflicting_results(feedbacks))

    def test_f3_rejected_wins_and_keeps_each_feedback(self):
        self.save('case-A', 'tb1.xml', notice_xml('Tiếp nhận hồ sơ'))
        self.save('case-A', 'tb2.xml', notice_xml('Không chấp nhận hồ sơ', status='N', reason='Sai chỉ tiêu'))
        feedbacks = feedbacks_from_row(self.row(), taxpayer_key='mst-A')
        self.assertEqual(aggregate_feedback_result(feedbacks), BUSINESS_REJECTED)
        self.assertEqual({item.business_result for item in feedbacks},
                         {BUSINESS_RECEIVED, BUSINESS_REJECTED})
        self.assertFalse(has_conflicting_results(feedbacks))

    def test_accepted_and_rejected_together_are_flagged_for_review(self):
        self.save('case-A', 'tb1.xml', notice_xml('Chấp nhận hồ sơ'))
        self.save('case-A', 'tb2.xml', notice_xml('Không chấp nhận hồ sơ', status='N'))
        feedbacks = feedbacks_from_row(self.row(), taxpayer_key='mst-A')
        self.assertEqual(aggregate_feedback_result(feedbacks), BUSINESS_REJECTED)
        self.assertTrue(has_conflicting_results(feedbacks))

    def test_downloaded_zip_never_implies_accepted(self):
        row = self.row(_file_status=DOWNLOAD_DOWNLOADED)
        submission = submission_from_row(row, taxpayer_key='mst-A')
        self.assertEqual(submission.download_status, DOWNLOAD_DOWNLOADED)
        self.assertEqual(submission.tax_processing_status, BUSINESS_NONE)


class IdentityTests(ContractTestBase):
    def test_f4_two_submissions_same_period_have_distinct_keys(self):
        first = self.row('case-A', ky_tinh_thue='Quý 3/2026', ngay_nop='20/10/2026')
        second = self.row('case-B', ky_tinh_thue='Quý 3/2026', ngay_nop='20/10/2026',
                          lan_nop='Bổ sung lần 1')
        self.assertNotEqual(submission_key(first, taxpayer_key='mst-A'),
                            submission_key(second, taxpayer_key='mst-A'))
        self.assertEqual(submission_from_row(first, taxpayer_key='mst-A').tax_period, 'Quý 3/2026')

    def test_f5_two_same_type_feedbacks_are_kept_separately(self):
        self.save('case-A', 'tb1.xml', notice_xml('Chấp nhận hồ sơ', number='111/TB'))
        self.save('case-A', 'tb2.xml', notice_xml('Chấp nhận hồ sơ', number='222/TB'))
        feedbacks = feedbacks_from_row(self.row(), taxpayer_key='mst-A')
        self.assertEqual(len(feedbacks), 2)
        self.assertEqual(len({item.feedback_key for item in feedbacks}), 2)
        self.assertEqual({item.business_result for item in feedbacks}, {BUSINESS_ACCEPTED})
        self.assertEqual({item.notice_number for item in feedbacks}, {'111/TB', '222/TB'})

    def test_f10_same_filename_in_two_submissions_keeps_distinct_keys(self):
        self.save('case-A', 'tb.xml', notice_xml('Chấp nhận hồ sơ'))
        self.save('case-B', 'tb.xml', notice_xml('Chấp nhận hồ sơ'))
        first = feedbacks_from_row(self.row('case-A'), taxpayer_key='mst-A')[0]
        second = feedbacks_from_row(self.row('case-B'), taxpayer_key='mst-A')[0]
        self.assertNotEqual(first.feedback_key, second.feedback_key)
        self.assertNotEqual(first.submission_key, second.submission_key)

    def test_f11_multiple_taxpayers_never_share_keys(self):
        row_a = self.row('case-A')
        row_b = self.row('case-A')
        self.assertNotEqual(submission_key(row_a, taxpayer_key='mst-A'),
                            submission_key(row_b, taxpayer_key='mst-B'))
        self.assertNotEqual(tax_notice_key({'message_id': '1'}, taxpayer_key='mst-A'),
                            tax_notice_key({'message_id': '1'}, taxpayer_key='mst-B'))


class SourceIsolationTests(ContractTestBase):
    def test_f6_independent_tax_notice_is_not_a_submission_feedback(self):
        notice = ThongBao('msg-1', ma_tbao='01', so_thong_bao='999/TB',
                          ten_thong_bao='Thông báo nộp thuế', ngay_gui='20/10/2026')
        row = notice.to_dict()
        row.update(_file_status=DOWNLOAD_DOWNLOADED, _file_path='', _file_hash='abc', _file_size=10)
        mapped = tax_notice_from_row(row, taxpayer_key='mst-A')
        self.assertIn('message_id=msg-1', mapped.tax_notice_key)
        self.assertNotIn('source=DVC', mapped.tax_notice_key)
        self.assertEqual(mapped.business_result, BUSINESS_UNKNOWN)
        self.assertEqual(feedbacks_from_row(row, taxpayer_key='mst-A'), [])
        self.assertNotEqual(mapped.tax_notice_key,
                            submission_key({'ma_ho_so': 'msg-1', 'nguon': SOURCE_TB}, taxpayer_key='mst-A'))

    def test_asset_owner_kinds_do_not_mix(self):
        self.save('case-A', 'tb.xml', notice_xml('Chấp nhận hồ sơ'))
        row = self.row(_file_path=str(self.root / 'case.zip'), tep_zip='case.zip',
                       _file_hash='hash', _file_size=42, _file_status=DOWNLOAD_DOWNLOADED)
        feedback_asset, = assets_from_row(row, taxpayer_key='mst-A')
        source_asset = declaration_asset(row, taxpayer_key='mst-A')
        notice_row = ThongBao('msg-1').to_dict()
        notice_row.update(_file_status=DOWNLOAD_DOWNLOADED, _file_path='', _file_hash='h', _file_size=1)
        notice_asset = tax_notice_asset(notice_row, taxpayer_key='mst-A')
        self.assertEqual(feedback_asset.owner_kind, OWNER_FEEDBACK)
        self.assertEqual(source_asset.owner_kind, OWNER_DECLARATION)
        self.assertEqual(notice_asset.owner_kind, OWNER_TAX_NOTICE)
        self.assertEqual(len({feedback_asset.owner_kind, source_asset.owner_kind,
                              notice_asset.owner_kind}), 3)


class ParsingAndIntegrityTests(ContractTestBase):
    def test_f7_corrupt_xml_and_unknown_status_never_become_accepted(self):
        self.save('case-A', 'broken.xml', b'<broken>')
        self.save('case-A', 'unknown.xml', notice_xml('Chấp nhận hồ sơ', status='NEW_STATUS'))
        feedbacks = feedbacks_from_row(self.row(), taxpayer_key='mst-A')
        self.assertEqual(len(feedbacks), 2)
        self.assertEqual(aggregate_feedback_result(feedbacks), BUSINESS_UNKNOWN)
        self.assertTrue(all(item.business_result == BUSINESS_UNKNOWN for item in feedbacks))

    def test_f8_namespaced_unicode_xml_parses_without_guessing(self):
        self.save('case-A', 'tb.xml', notice_xml('Chấp nhận hồ sơ', number='77/TB',
                                                 namespace=True))
        feedback, = feedbacks_from_row(self.row(), taxpayer_key='mst-A')
        self.assertEqual(feedback.feedback_type, BUSINESS_ACCEPTED)
        self.assertEqual(feedback.business_result, BUSINESS_ACCEPTED)
        self.assertEqual(feedback.notice_number, '77/TB')
        self.assertEqual(feedback.issued_at, '2026-09-11')

    def test_f9_nested_reason_is_preserved_in_metadata(self):
        self.save('case-A', 'tb.xml', notice_xml('Không chấp nhận hồ sơ', status='N',
                                                 reason='Sai chỉ tiêu [22]'))
        feedback, = feedbacks_from_row(self.row(), taxpayer_key='mst-A')
        self.assertEqual(feedback.business_result, BUSINESS_REJECTED)
        self.assertEqual(feedback.source_metadata['ly_do'], 'Sai chỉ tiêu [22]')

    def test_integrity_states_are_independent_of_business_result(self):
        self.save('case-A', 'tb.xml', notice_xml('Chấp nhận hồ sơ'))
        notice = read_notices(self.root, 'case-A')[0]
        self.assertEqual(notice['reference_status'], 'LEGACY_UNVERIFIED')
        asset = assets_from_row(self.row(), taxpayer_key='mst-A')[0]
        self.assertEqual(asset.integrity_status, INTEGRITY_UNVERIFIED)
        self.assertEqual(asset.checksum, notice['sha256'])
        self.assertNotIn('chữ ký', INTEGRITY_LABELS[INTEGRITY_VERIFIED].casefold())

    def test_tampered_file_is_invalid_and_not_used_for_verdict(self):
        import json

        path = self.save('case-A', 'tb.xml', notice_xml('Chấp nhận hồ sơ'))
        info = {'source': {'parent_remote_id': 'case-A', 'parent_record_key': 'parent-A',
                           'record_key': 'attachment-1'},
                'size': path.stat().st_size, 'sha256': '0' * 64, 'status': 'OK'}
        path.with_name(path.name + '.integrity.json').write_text(json.dumps(info), encoding='utf-8')
        notices = read_notices(self.root, 'case-A', parent_key='parent-A')
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]['reference_status'], 'INVALID')
        self.assertEqual(notices[0]['state'], '')
        asset = assets_from_row({'ma_ho_so': 'case-A', '_notices': notices}, taxpayer_key='mst-A')[0]
        self.assertEqual(asset.integrity_status, INTEGRITY_INVALID)
        feedback, = feedbacks_from_row({'ma_ho_so': 'case-A', '_notices': notices}, taxpayer_key='mst-A')
        self.assertEqual(feedback.business_result, BUSINESS_UNKNOWN)


class DateSemanticsTests(ContractTestBase):
    def test_submitted_date_and_tax_period_are_distinct(self):
        row = self.row('case-A', ngay_nop='20/10/2026', ky_tinh_thue='Quý 3/2026')
        submission = submission_from_row(row, taxpayer_key='mst-A')
        self.assertEqual(submission.submitted_at, '20/10/2026')
        self.assertEqual(submission.tax_period, 'Quý 3/2026')
        self.assertNotEqual(submission.submitted_at, submission.tax_period)

    def test_business_status_text_mapping_is_conservative(self):
        self.assertEqual(business_status_from_text('Đã tiếp nhận hồ sơ'), BUSINESS_RECEIVED)
        self.assertEqual(business_status_from_text('Hồ sơ được chấp nhận'), BUSINESS_ACCEPTED)
        self.assertEqual(business_status_from_text('Không chấp nhận hồ sơ'), BUSINESS_REJECTED)
        self.assertEqual(business_status_from_text('Đang xử lý'), BUSINESS_UNKNOWN)
        self.assertEqual(business_status_from_text(''), BUSINESS_UNKNOWN)


class OwnershipTests(ContractTestBase):
    def test_parent_key_mismatch_does_not_claim_verified_result(self):
        import hashlib
        import json

        path = self.save('case-A', 'tb.xml', notice_xml('Chấp nhận hồ sơ'))
        info = {'source': {'parent_remote_id': 'case-A', 'parent_record_key': 'other-parent',
                           'record_key': 'attachment-1'},
                'size': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'status': 'OK'}
        path.with_name(path.name + '.integrity.json').write_text(json.dumps(info), encoding='utf-8')
        notice = read_notices(self.root, 'case-A', parent_key='expected-parent')
        self.assertEqual(notice, [])


if __name__ == '__main__':
    unittest.main()
