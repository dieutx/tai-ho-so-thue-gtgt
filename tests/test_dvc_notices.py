"""Thông báo đính kèm hồ sơ DVC: đọc modal, tải JSON base64 và lưu tệp."""

from __future__ import annotations

import base64
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from gdt_tax.config import Settings
from gdt_tax.constants import (
    DVC_DOWNLOAD,
    DVC_NOTICE_DOWNLOAD,
    DVC_SEARCH,
    DVC_VALIDATE,
)
from gdt_tax.dvc_notices import (
    LOAI_CHAP_NHAN,
    LOAI_KHAC,
    LOAI_KHONG_CHAP_NHAN,
    LOAI_TIEP_NHAN,
    NoticeStore,
    decode_notice_response,
    notice_filename,
    parse_notices,
)
from gdt_tax.pipeline import Pipeline
from gdt_tax.portals.dvc import DvcPortal
from gdt_tax.storage import ZipStore
from tests.support import (
    FakeHttp,
    FakeResponse,
    StubCaptcha,
    cleanup_temporary_directory,
    route_of,
    zip_payload,
)
from tests.test_pipeline import dvc_search, make_handler

NOTICE_XML = b'<?xml version="1.0" encoding="UTF-8"?><TBaoThue><MaTB>8198</MaTB></TBaoThue>'
NOTICE_B64 = base64.b64encode(NOTICE_XML).decode("ascii")

DETAIL_HTML = """
<html><body>
<input type="hidden" name="_csrf" value="csrf-detail"/>
<div class="modal fade" id="modalThongBao">
  <div class="modal-body row align-items-center">
    <div class="row">
      <div class="col-md-9 mb-3">
        <div class="fw-bold">V/v: Tiếp nhận hồ sơ thuế điện tử TT19</div>
        <div>09:57 11/09/2026</div>
      </div>
      <div class="col-md-3 text-md-end text-center mb-3">
        <a class="bi bi-download" href="#" onclick="downloadThongBao(this); return false;"
           data-id="10820260069828466">Tải xuống</a>
      </div>
    </div>
    <div class="row">
      <div class="col-md-9 mb-3">
        <div class="fw-bold">V/v: Xác nhận nộp hồ sơ thuế điện tử TT19</div>
        <div>15:00 11/09/2026</div>
      </div>
      <div class="col-md-3 text-md-end text-center mb-3">
        <a class="bi bi-download" href="#" onclick="downloadThongBao(this); return false;"
           data-id="10820260069884825">Tải xuống</a>
      </div>
    </div>
    <div class="row">
      <div class="col-md-9 mb-3">
        <div class="fw-bold">V/v: Không chấp nhận hồ sơ thuế điện tử TT19</div>
        <div>16:10 11/09/2026</div>
      </div>
      <div class="col-md-3 text-md-end text-center mb-3">
        <a class="bi bi-download" href="#" onclick="downloadThongBao(this); return false;"
           data-id="10820260069890001">Tải xuống</a>
      </div>
    </div>
  </div>
</div>
</body></html>
"""


class NoticeParsingTests(unittest.TestCase):
    def test_reads_all_notifications_and_classifies_them(self):
        notices = parse_notices(DETAIL_HTML)
        self.assertEqual([item.id for item in notices],
                         ["10820260069828466", "10820260069884825", "10820260069890001"])
        self.assertEqual([item.loai for item in notices],
                         [LOAI_TIEP_NHAN, LOAI_CHAP_NHAN, LOAI_KHONG_CHAP_NHAN])
        self.assertEqual(notices[0].title, "Tiếp nhận hồ sơ thuế điện tử TT19")
        self.assertEqual(notices[0].sent_at, "09:57 11/09/2026")

    def test_combined_acceptance_title_is_not_labeled_rejected(self):
        html = DETAIL_HTML.replace(
            "V/v: Không chấp nhận hồ sơ thuế điện tử TT19",
            "V/v: Chấp nhận/Không chấp nhận về việc nộp hồ sơ khai thuế điện tử",
        )
        self.assertEqual(parse_notices(html)[2].loai, LOAI_KHAC)

    def test_ignores_pages_without_the_notification_modal(self):
        self.assertEqual(parse_notices("<html><body>Không có thông báo</body></html>"), [])
        self.assertEqual(parse_notices(""), [])

    def test_filename_starts_with_notice_id_and_classification(self):
        notice = parse_notices(DETAIL_HTML)[0]
        name = notice_filename("G12.18-260911-00028255", notice, "xml")
        self.assertTrue(name.startswith("10820260069828466__tiep-nhan__G12.18-260911-00028255"))
        self.assertTrue(name.endswith(".xml"))


class NoticeDecodeTests(unittest.TestCase):
    def test_decodes_json_base64_payload(self):
        payload = decode_notice_response(FakeResponse(json_payload={
            "fileName": "Thong bao_10820260069828466.xml",
            "fileType": "xml",
            "content": NOTICE_B64,
        }))
        self.assertIsNotNone(payload)
        self.assertEqual(payload.data, NOTICE_XML)
        self.assertEqual(payload.extension, "xml")

    def test_rejects_error_and_empty_payloads(self):
        self.assertIsNone(decode_notice_response(FakeResponse("loi", status_code=500)))
        self.assertIsNone(decode_notice_response(FakeResponse(json_payload={"content": ""})))
        self.assertIsNone(decode_notice_response(FakeResponse(json_payload={"content": "@@@"})))


class NoticeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def test_saves_per_case_and_reuses_by_notice_id(self):
        store = NoticeStore(self.root)
        notice = parse_notices(DETAIL_HTML)[0]
        payload = decode_notice_response(FakeResponse(json_payload={
            "fileName": "Thong bao.xml", "fileType": "xml", "content": NOTICE_B64,
        }))
        path = store.save("G12.18-260911-00028255", notice, payload)
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent, self.root / "G12.18-260911-00028255")
        self.assertEqual(store.find_existing("G12.18-260911-00028255", notice.id), path)
        self.assertIsNone(store.find_existing("G12.18-260911-00028255", "khac"))


class NoticePortalTests(unittest.TestCase):
    def test_posts_id_and_csrf_for_each_endpoint(self):
        def handler(method, path, kwargs):
            route = route_of(path)
            if route in {DVC_NOTICE_DOWNLOAD, "/tchs/downloadthongbao-tdt"}:
                return FakeResponse(json_payload={
                    "fileName": "Thong bao.xml", "fileType": "xml", "content": NOTICE_B64,
                })
            return None

        http = FakeHttp(handler)
        portal = DvcPortal(http, StubCaptcha(), SimpleNamespace(header_profile="minimal"))
        portal.detail_html = DETAIL_HTML
        notices = portal.fetch_notices()
        payload = portal.download_notice(notices[0], "https://example.test/tthc/tchs/files/detail/X", "csrf-detail")
        self.assertEqual(payload.data, NOTICE_XML)
        call = http.calls[-1]
        self.assertEqual(call.path, DVC_NOTICE_DOWNLOAD)
        self.assertEqual(call.kwargs["json"], {"idTbao": "10820260069828466", "loaiTBao": ""})
        self.assertEqual(call.kwargs["headers"]["X-XSRF-TOKEN"], "csrf-detail")

        tdt_html = DETAIL_HTML.replace(
            'data-id="10820260069884825"',
            'data-id="10820260069884825" data-is-thue-dien-tu="true" data-loaitracuu="ETAX"',
        )
        portal.detail_html = tdt_html
        portal.download_notice(portal.fetch_notices()[1], "https://example.test/detail", "csrf-detail")
        call = http.calls[-1]
        self.assertEqual(call.path, "/tchs/downloadthongbao-tdt")
        self.assertEqual(call.kwargs["params"], {"loaiTraCuu": "ETAX"})


class NoticePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = Settings(
            username="synthetic-taxpayer-QL",
            password="mat-khau",
            from_date=date(2026, 1, 1),
            to_date=date(2026, 1, 31),
            download_dir=self.root,
            login_attempts=1,
            search_attempts=1,
            pause_between_records=0.0,
            pause_between_pages=0.0,
            dvc_enabled=True,
            legacy_etax=False,
        )

    def tearDown(self):
        cleanup_temporary_directory(self.temp)

    def handler(self):
        base = make_handler(search=dvc_search)

        def handler(method, path, kwargs):
            route = route_of(path)
            if route.startswith("/tchs/files/detail/"):
                return FakeResponse(DETAIL_HTML)
            if route == DVC_NOTICE_DOWNLOAD:
                return FakeResponse(json_payload={
                    "fileName": "Thong bao.xml", "fileType": "xml", "content": NOTICE_B64,
                })
            if route == DVC_VALIDATE:
                return FakeResponse("200")
            if route == DVC_DOWNLOAD:
                return FakeResponse(json_payload={"content": zip_payload()})
            if route == DVC_SEARCH:
                return FakeResponse(dvc_search(kwargs))
            return base(method, path, kwargs)

        return handler

    def run_pipeline(self):
        http = FakeHttp(self.handler())
        pipeline = Pipeline(self.settings, http, StubCaptcha(),
                            store=ZipStore(self.root), sleep=lambda _seconds: None)
        return pipeline.run(), http

    def test_downloads_receipt_and_acceptance_notices_beside_each_case(self):
        summary, http = self.run_pipeline()
        self.assertEqual(summary.downloaded, 2)
        zip_files = list(self.root.glob("*.zip"))
        self.assertEqual(len(zip_files), 2)
        for case in {path.stem.split("__")[0] for path in zip_files}:
            folder = self.root / "thong-bao-dinh-kem" / case
            names = sorted(path.name for path in folder.glob("*.xml"))
            self.assertEqual(len(names), 3, names)
            self.assertTrue(any("tiep-nhan" in name for name in names))
            self.assertTrue(any("chap-nhan" in name for name in names))
            self.assertTrue(any("khong-chap-nhan" in name for name in names))
        posts = [call for call in http.calls if route_of(call.path) == DVC_NOTICE_DOWNLOAD]
        self.assertEqual(len(posts), 6)

    def test_second_run_reuses_notice_files_without_downloading_again(self):
        self.run_pipeline()
        summary, http = self.run_pipeline()
        self.assertEqual(summary.downloaded, 2)
        posts = [call for call in http.calls if route_of(call.path) == DVC_NOTICE_DOWNLOAD]
        self.assertEqual(posts, [])


if __name__ == "__main__":
    unittest.main()
