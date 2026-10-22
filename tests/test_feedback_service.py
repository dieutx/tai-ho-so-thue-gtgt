"""S02: selector phản hồi theo đúng lần nộp và thông báo thuế độc lập."""
from __future__ import annotations

import unittest

from desktop.domain import BUSINESS_NONE, BUSINESS_REJECTED
from desktop.feedback_service import (
    RequestGate,
    feedback_summary,
    find_feedback_item,
    find_tax_notice_asset,
    get_feedback_for_submission,
    list_feedback_assets,
    list_feedback_items,
    list_tax_notice_assets,
    list_tax_notices,
)


def notice(name: str, *, kind: str = 'chap-nhan', state: str = 'accepted',
           number: str = '', issued: str = '', reference_key: str = '',
           relative_path: str | None = None, read_status: str = 'PARSED') -> dict:
    return {
        'path': 'C:/ho-so/' + name,
        'name': name,
        'kind': kind,
        'kind_label': kind,
        'state': state,
        'parent_key': '',
        'reference_key': reference_key,
        'relative_path': relative_path or f'thong-bao-dinh-kem/case-A/{name}',
        'reference_status': 'LEGACY_UNVERIFIED',
        'sha256': 'abc',
        'size': 10,
        'read_status': read_status,
        'ma_thong_bao': '',
        'so_thong_bao': number,
        'ten_thong_bao': '',
        'ngay_thong_bao': issued,
        'ly_do': '',
    }


def tax_row(notices=None, **extra) -> dict:
    row = {'ma_ho_so': 'case-A', 'nguon': 'DVC', 'ky_tinh_thue': 'Quý 3/2026',
           'ngay_nop': '20/10/2026', 'to_khai': '01/GTGT', '_file_status': 'not_downloaded'}
    row.update(extra)
    if notices is not None:
        row['_notices'] = notices
    return row


class FeedbackSelectorTests(unittest.TestCase):
    def test_no_feedback_returns_empty_and_none(self):
        row = tax_row([])
        self.assertEqual(get_feedback_for_submission(row, taxpayer_key='mst-A'), [])
        self.assertEqual(list_feedback_assets(row, taxpayer_key='mst-A'), [])
        summary = feedback_summary(row, taxpayer_key='mst-A')
        self.assertEqual(summary.count, 0)
        self.assertEqual(summary.status, BUSINESS_NONE)

    def test_missing_notices_field_is_treated_as_empty(self):
        row = tax_row()
        self.assertEqual(get_feedback_for_submission(row, taxpayer_key='mst-A'), [])

    def test_feedback_newest_first_and_keys_match_assets(self):
        row = tax_row([
            notice('old.xml', number='1/TB', issued='2026-09-11'),
            notice('new.xml', number='2/TB', issued='2026-09-12'),
        ])
        items = list_feedback_items(row, taxpayer_key='mst-A')
        self.assertEqual([item.feedback.notice_number for item in items], ['2/TB', '1/TB'])
        for item in items:
            self.assertEqual(item.feedback.feedback_key, item.asset.asset_key)
            self.assertEqual(item.feedback.submission_key, item.asset.owner_key)

    def test_duplicate_reference_key_is_not_silently_dropped(self):
        row = tax_row([
            notice('a.xml', reference_key='same', relative_path='thong-bao-dinh-kem/case-A/a.xml'),
            notice('b.xml', reference_key='same', relative_path='thong-bao-dinh-kem/case-A/b.xml'),
        ])
        items = list_feedback_items(row, taxpayer_key='mst-A')
        self.assertEqual(len(items), 2)
        self.assertEqual(len({item.feedback.feedback_key for item in items}), 2)
        self.assertEqual({item.asset.asset_key for item in items},
                         {item.feedback.feedback_key for item in items})

    def test_find_feedback_uses_stable_key(self):
        row = tax_row([
            notice('a.xml', reference_key='ref-a', number='A/TB', issued='2026-09-11'),
            notice('b.xml', reference_key='ref-b', number='B/TB', issued='2026-09-12'),
        ])
        item = find_feedback_item(row, 'ref-a', taxpayer_key='mst-A')
        self.assertIsNotNone(item)
        self.assertEqual(item.feedback.notice_number, 'A/TB')
        self.assertIsNone(find_feedback_item(row, 'missing', taxpayer_key='mst-A'))

    def test_conflict_is_flagged_but_individual_rows_are_kept(self):
        row = tax_row([
            notice('accept.xml', state='accepted', issued='2026-09-11'),
            notice('reject.xml', kind='khong-chap-nhan', state='rejected', issued='2026-09-12'),
        ])
        summary = feedback_summary(row, taxpayer_key='mst-A')
        self.assertEqual(summary.status, BUSINESS_REJECTED)
        self.assertTrue(summary.conflict)
        self.assertEqual(summary.count, 2)

    def test_incomplete_attachment_problem_is_surfaced(self):
        row = tax_row([], attachment_result={
            'status': 'PARTIAL', 'downloaded': 0, 'reused': 0, 'discovered': 2,
            'failed': 1, 'items': [{'code': 'ATTACHMENT_RATE_LIMITED'}]})
        self.assertIn('Thông báo chưa đầy đủ', feedback_summary(row, taxpayer_key='mst-A').problem)


class TaxNoticeSelectorTests(unittest.TestCase):
    def test_declaration_feedback_never_leaks_into_tax_notices(self):
        declaration = tax_row([notice('accept.xml')])
        independent = {
            'message_id': 'msg-1', 'ma_tbao': '01', 'so_thong_bao': '999/TB',
            'ten_thong_bao': 'Thông báo nộp thuế', 'ngay_gui': '20/10/2026',
            'ky_tinh_thue': 'Quý 3/2026', '_file_status': 'downloaded',
        }
        notices = list_tax_notices([declaration, independent], taxpayer_key='mst-A')
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0].number, '999/TB')
        self.assertEqual([item.feedback_key for item in get_feedback_for_submission(declaration,
                                                                                   taxpayer_key='mst-A')],
                         ['thong-bao-dinh-kem/case-A/accept.xml'])

    def test_tax_notices_dedupe_by_key_and_sort_newest_first(self):
        older = {'message_id': 'msg-1', 'so_thong_bao': '1/TB', 'ngay_gui': '01/05/2026'}
        newer = {'message_id': 'msg-2', 'so_thong_bao': '2/TB', 'ngay_gui': '01/06/2026'}
        duplicate = dict(older)
        notices = list_tax_notices([older, newer, duplicate], taxpayer_key='mst-A')
        self.assertEqual([item.number for item in notices], ['2/TB', '1/TB'])
        self.assertEqual(len(list_tax_notice_assets([older, newer, duplicate],
                                                    taxpayer_key='mst-A')), 2)

    def test_tax_notice_asset_has_own_owner_kind(self):
        row = {'message_id': 'msg-1', 'so_thong_bao': '1/TB', 'ngay_gui': '01/05/2026',
               '_file_status': 'downloaded', '_file_path': 'C:/ho-so/notice.pdf',
               '_file_hash': 'h', '_file_size': 5}
        asset = find_tax_notice_asset(row, taxpayer_key='mst-A')
        self.assertIsNotNone(asset)
        self.assertEqual(asset.owner_kind, 'tax_notice')
        self.assertEqual(asset.original_filename, 'notice.pdf')
        self.assertIsNone(find_tax_notice_asset({'ma_ho_so': 'case-A'}, taxpayer_key='mst-A'))


class RequestGateTests(unittest.TestCase):
    def test_stale_token_is_rejected_after_invalidate(self):
        gate = RequestGate()
        first = gate.begin()
        self.assertTrue(gate.is_current(first))
        gate.invalidate()
        self.assertFalse(gate.is_current(first))
        second = gate.begin()
        self.assertTrue(gate.is_current(second))


if __name__ == '__main__':
    unittest.main()
