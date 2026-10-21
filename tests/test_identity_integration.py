"""Synthetic scoped identity collisions across real pipeline/store/GUI consumers."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from desktop.documents import document_id, remote_document_id
from desktop.services import RunConfig
from desktop.sessions import ETaxSessionManager
from gdt_tax.config import Settings
from gdt_tax.dvc_notices import DvcNotice, NoticeFile, NoticeStore
from gdt_tax.gnt.models import GiayNopTien
from gdt_tax.identity import IdentityError, RecordKey, account_fingerprint
from gdt_tax.models import CaseRecord, PageResult
from gdt_tax.pipeline import Pipeline
from gdt_tax.storage import ZipStore, write_metadata
from gdt_tax.table_contracts import ParseDiagnostics
from gdt_tax.tb.models import ThongBao
from tests.support import (
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    cleanup_temporary_directory,
    sample_zip,
)


class FixturePortal:
    def __init__(self, source, downloads):
        self.source, self.downloads = source, downloads

    def search(self, period, page):
        return PageResult([CaseRecord("same-id", self.source, to_khai="synthetic declaration")], 1, 200,
                          ParseDiagnostics("PARSED", 1, 1))

    def fetch_detail_csrf(self, record):
        return "https://example.test/detail", "fake-csrf"

    def download(self, record, detail_url, csrf):
        self.downloads.append((self.source, record.ma_ho_so))
        return FakeResponse(content=sample_zip())


class IdentityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.account = account_fingerprint("synthetic-account-a")
        self.settings = Settings("synthetic-account-a", "fake-secret", date(2025, 6, 30), date(2025, 7, 1),
                                 self.root, dvc_enabled=True, legacy_etax=False,
                                 pause_between_records=0, pause_between_pages=0)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def pipeline(self, targets=None, settings=None):
        downloads = []
        portals = {source: FixturePortal(source, downloads) for source in ("ETAX", "DVC")}
        pipeline = Pipeline(settings or self.settings, FakeHttp(lambda *_: None), StubCaptcha(),
                            portal_factory=lambda *_: portals, target_ids=targets)
        return pipeline, downloads

    def run_pipeline(self, pipeline):
        with patch("gdt_tax.pipeline.login", return_value=True), patch("gdt_tax.pipeline.open_landing", return_value=""):
            return pipeline.run()

    def test_same_remote_id_on_two_sources_remains_two_downloads_and_files(self):
        pipeline, downloads = self.pipeline()
        summary = self.run_pipeline(pipeline)
        self.assertTrue(summary.complete)
        self.assertEqual((summary.discovered, summary.downloaded), (2, 2))
        self.assertEqual(downloads, [("ETAX", "same-id"), ("DVC", "same-id")])
        self.assertEqual(len(pipeline.downloaded_ids), 2)
        self.assertEqual(len(list(self.root.glob("*.zip"))), 2)
        rows = json.loads((self.root / "danh_sach_ho_so.json").read_text(encoding="utf-8"))
        self.assertEqual({RecordKey.parse(row["record_key"]).source for row in rows}, {"ETAX", "DVC"})
        again, second_downloads = self.pipeline()
        self.run_pipeline(again)
        self.assertEqual(second_downloads, [])
        self.assertEqual(len(again.reused_ids), 2)

    def test_selecting_dvc_does_not_download_etax_with_same_id(self):
        selected = RecordKey(self.account, "DVC", "DECLARATION", "same-id").serialize()
        pipeline, downloads = self.pipeline({selected})
        summary = self.run_pipeline(pipeline)
        self.assertTrue(summary.complete)
        self.assertEqual(summary.expected, 1)
        self.assertEqual(downloads, [("DVC", "same-id")])
        rows = [record.to_dict() for record in pipeline.records.values()]
        self.assertEqual(len({document_id("tax", row) for row in rows}), 2)
        self.assertTrue(all(remote_document_id("tax", row) == "same-id" for row in rows))

    def test_bare_multisource_and_cross_account_targets_fail_before_login(self):
        invalid = [{"same-id"}, {RecordKey("wrong-account", "DVC", "DECLARATION", "same-id").serialize()}]
        for targets in invalid:
            pipeline, downloads = self.pipeline(targets)
            with patch("gdt_tax.pipeline.login") as login:
                with self.assertRaises(IdentityError):
                    pipeline.run()
                login.assert_not_called()
            self.assertEqual(downloads, [])

    def test_session_manager_checks_target_account_before_authentication(self):
        config = RunConfig("tax", self.root, username="synthetic-account-a", password="fake-secret",
            target_ids=(RecordKey("wrong-account", "ETAX_LEGACY", "DECLARATION", "same-id").serialize(),))
        manager = ETaxSessionManager()
        with patch.object(manager, "ensure_authenticated") as login:
            with self.assertRaises(IdentityError):
                manager.execute(config, Mock(), StubCaptcha())
            login.assert_not_called()
        manager.close()

    def test_known_account_never_reuses_unknown_or_other_account_file(self):
        store = ZipStore(self.root)
        unknown = CaseRecord("same-id", "DVC")
        original = store.save(unknown, sample_zip())
        known = replace(unknown, account_key=self.account)
        self.assertIsNone(store.find_existing(known))
        new = store.save(known, sample_zip())
        self.assertNotEqual(new, original)
        self.assertTrue(original.exists())
        other = replace(known, account_key=account_fingerprint("synthetic-account-b"))
        self.assertIsNone(store.find_existing(other))
        self.assertEqual(store.find_existing(known), new)

    def test_catalog_preserves_accounts_sources_and_unowned_legacy_rows(self):
        path = self.root / "danh_sach_ho_so.json"
        old = {"ma_ho_so": "same-id", "nguon": "DVC", "tep_zip": "legacy.zip"}
        path.write_text(json.dumps([old]), encoding="utf-8")
        rows = [CaseRecord("same-id", source, account_key=account) for source, account in (
            ("DVC", self.account), ("ETAX", self.account), ("DVC", account_fingerprint("synthetic-account-b")))]
        write_metadata(self.root, rows)
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 4)
        self.assertIn(old, payload)
        self.assertEqual(len({row["record_key"] for row in payload if row.get("record_key")}), 3)

    def test_notice_identity_keeps_same_remote_id_on_different_parents_and_accounts(self):
        store = NoticeStore(self.root)
        parent = RecordKey(self.account, "DVC", "DECLARATION", "same-parent-id")
        notice = DvcNotice("same-notice-id", title="synthetic")
        payload = NoticeFile("notice.xml", b"<TBao/>", "xml")
        path = store.save(parent, notice, payload)
        changed = replace(parent, account_key=account_fingerprint("synthetic-account-b"))
        self.assertIsNone(store.find_existing(changed, notice))
        changed_source = replace(parent, source="ETAX")
        self.assertIsNone(store.find_existing(changed_source, notice))
        self.assertEqual(store.find_existing(parent, replace(notice, title="new human title")), path)

    def test_dry_run_across_sources_does_not_create_catalog_or_sidecars(self):
        destination = self.root / "not-created"
        pipeline, downloads = self.pipeline(settings=replace(self.settings, dry_run=True, download_dir=destination))
        self.run_pipeline(pipeline)
        self.assertEqual(downloads, [])
        self.assertFalse(destination.exists())

    def test_same_remote_id_on_two_document_kinds_has_distinct_gui_identity(self):
        gnt = GiayNopTien("same-id", account_key=self.account).to_dict()
        notice = ThongBao("same-id", account_key=self.account).to_dict()
        self.assertNotEqual(document_id("gnt", gnt), document_id("notice", notice))
        self.assertEqual(RecordKey.parse(document_id("gnt", gnt)).document_kind, "GNT")
        self.assertEqual(RecordKey.parse(document_id("notice", notice)).document_kind, "NOTICE")
