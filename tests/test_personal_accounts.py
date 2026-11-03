"""Tài khoản cá nhân: DSE canhan.gdt.gov.vn theo HAR đã xác minh.

Test dùng HTML/XML tổng hợp, không đọc HAR, không chứa MST/mật khẩu/tên thật.
"""
from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from gdt_tax.config import Settings
from gdt_tax.identity import account_fingerprint
from gdt_tax.models import CaseRecord
from gdt_tax.portals.canhan import CanhanPortal, parse_declarations, parse_notices
from gdt_tax.tb.models import ThongBao
from gdt_tax.tb.storage import TbStore
from tests.support import FakeHttp, FakeResponse, StubCaptcha

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

LOGIN_FORM = """
<form id="loginForm" action="Request" method="post">
  <input type="hidden" name="dse_sessionId" value="s1">
  <input type="hidden" name="dse_applicationId" value="-1">
  <input type="hidden" name="dse_operationName" value="retailUserLoginProc">
  <input type="hidden" name="dse_pageId" value="6">
  <input type="hidden" name="dse_processorState" value="checkloginpage">
  <input type="hidden" name="dse_processorId" value="p1">
  <input type="hidden" name="dse_errorPage" value="error_page.jsp">
  <input type="hidden" name="dse_nextEventName" value="">
  <input type="text" name="_userName" value="">
  <input type="text" name="capcha" value="">
</form>
"""

PASSWORD_FORM = LOGIN_FORM.replace('value="6"', 'value="7"').replace(
    'checkloginpage', 'viewloginpage').replace(
    '<input type="text" name="_userName" value="">\n  <input type="text" name="capcha" value="">',
    '<input type="text" value="synthetic">\n  <input type="password" name="_password" value="">',
)

HOME_HTML = """
<html><body>Đăng xuất
<form id="goProcForm" action="/ICanhan/Request">
  <input type="hidden" name="dse_sessionId" value="s1">
  <input type="hidden" name="dse_applicationId" value="-1">
  <input type="hidden" name="dse_pageId" value="9">
  <input type="hidden" name="dse_operationName" value="retailHomePageProc">
  <input type="hidden" name="dse_processorState" value="initial">
  <input type="hidden" name="dse_nextEventName" value="start">
</form></body></html>
"""

DECLARATION_HTML = """
<html><body>
<form id="frm" action="Request">
  <input type="hidden" name="dse_sessionId" value="s1">
  <input type="hidden" name="dse_applicationId" value="-1">
  <input type="hidden" name="dse_pageId" value="11">
  <input type="hidden" name="dse_operationName" value="retailSearchVoucherProc">
  <input type="hidden" name="dse_processorState" value="searchTaxJsp">
  <input type="hidden" name="dse_processorId" value="p1">
  <input type="hidden" name="dse_nextEventName" value="">
</form>
<form id="frmtcuu" action="Request">
  <input type="hidden" name="dse_sessionId" value="s1">
  <input type="hidden" name="dse_applicationId" value="-1">
  <input type="hidden" name="dse_pageId" value="11">
  <input type="hidden" name="dse_operationName" value="retailSearchVoucherProc">
  <input type="hidden" name="dse_processorState" value="searchTaxJsp">
  <input type="hidden" name="dse_processorId" value="p1">
  <input type="hidden" name="dse_nextEventName" value="">
</form>
<table class="confirm_table">
<tr><th>STT</th><th>Mã giao dịch</th><th>Tờ khai/phụ lục</th><th>Kỳ tính thuế</th>
<th>Kỳ thanh toán từ ngày</th><th>Kỳ thanh toán đến ngày</th><th>Loại tờ khai</th>
<th>Lần nộp</th><th>Gửi phụ lục</th><th>Ngày nộp</th><th>Nơi nộp</th>
<th>Tiến trình giải quyết hồ sơ (Trạng thái)</th></tr>
<tr><td>1</td><td>11020250000000001</td><td>01/TTS- Tờ khai cho thuê tài sản</td>
<td>2025</td><td>01/01/2025</td><td>31/12/2025</td><td>Chính thức</td><td>1</td>
<td></td><td>19/11/2025 11:17:29</td><td>Thuế cơ sở 4</td>
<td>Cơ quan thuế chấp nhận hồ sơ</td></tr>
</table>
<a href="javascript: viewTKhai('11020250000000001');">Xem</a>
<a href="javascript: downloadGNT('11020250000000001','9');">Tải</a>
</body></html>
"""

NOTICE_HTML = """
<html><body>
<form id="frm" action="Request">
  <input type="hidden" name="dse_sessionId" value="s1">
  <input type="hidden" name="dse_pageId" value="18">
  <input type="hidden" name="dse_operationName" value="retailSearchTaxNoticesProc">
</form>
<table class="confirm_table">
<tr><th>STT</th><th>Mã giao dịch</th><th>Số thông báo</th><th>Thông báo</th>
<th>Ngày gửi</th><th>Tải về</th><th>Chi tiết</th></tr>
<tr><td>1</td><td>11020250000000001</td><td>238642/0111/2025/TB-TĐT</td>
<td>V/v Chấp nhận/Không chấp nhận</td><td>19/11/2025</td>
<td><a href="javascript: downloadGNT(85328477,'TK');">Tải</a></td><td></td></tr>
</table>
</body></html>
"""

XML = b'<?xml version="1.0" encoding="UTF-8"?><HSoThueDTu xmlns="http://kekhaithue.gdt.gov.vn/TKhaiThue"><HSoKhaiThue/></HSoThueDTu>'
NOTICE_XML = b'<?xml version="1.0" encoding="UTF-8"?><TBaoThueDTu xmlns="http://kekhaithue.gdt.gov.vn/TBaoThue"><TBaoThue/></TBaoThueDTu>'


def personal_settings(**overrides) -> Settings:
    return Settings.from_env(environ={}, env_file=None, username='synthetic-personal',
                             password='fixture', login_attempts=1, account_type='CN',
                             **overrides)


class PersonalParserTests(unittest.TestCase):
    def test_declaration_table_is_read_by_header_not_position(self):
        records = parse_declarations(DECLARATION_HTML)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.ma_ho_so, '11020250000000001')
        self.assertEqual(record.nguon, 'ETAX_LEGACY')
        self.assertEqual(record.ky_tinh_thue, '2025')
        self.assertEqual(record.loai_to_khai, 'Chính thức')
        self.assertEqual(record.ngay_nop, '19/11/2025 11:17:29')
        self.assertIn('chấp nhận', record.trang_thai)

    def test_notice_table_takes_download_id_and_kind_from_link(self):
        notices = parse_notices(NOTICE_HTML)
        self.assertEqual(len(notices), 1)
        notice = notices[0]
        self.assertEqual(notice.message_id, '85328477')
        self.assertEqual(notice.ma_tbao, 'TK')
        self.assertEqual(notice.so_thong_bao, '238642/0111/2025/TB-TĐT')
        self.assertEqual(notice.ngay_gui, '19/11/2025')


class PersonalDownloadTests(unittest.TestCase):
    def test_declaration_xml_is_wrapped_in_verified_zip(self):
        settings = personal_settings()
        portal = CanhanPortal(FakeHttp(lambda *_: None), StubCaptcha(), settings)
        portal._search_page_html = DECLARATION_HTML
        portal._search_page_url = 'https://canhan.gdt.gov.vn/ICanhan/Request'
        http = FakeHttp(lambda method, path, kwargs: FakeResponse(
            content=XML, headers={'content-type': 'application/octet-stream'},
            url='https://canhan.gdt.gov.vn/ICanhan/Request'))
        portal.http = http
        record = CaseRecord(ma_ho_so='11020250000000001', nguon='ETAX_LEGACY',
                            account_key=account_fingerprint('synthetic-personal'))
        artifact = portal.download(record, '', '')
        self.assertEqual(artifact.media_kind, 'zip')
        from gdt_tax.integrity import validate_tax_zip
        self.assertTrue(validate_tax_zip(artifact.data).ok)
        with zipfile.ZipFile(BytesIO(artifact.data)) as archive:
            self.assertEqual(archive.read('11020250000000001.xml'), XML)

    def test_personal_notice_store_accepts_xml_and_resumes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TbStore(directory)
            record = ThongBao(message_id='85328477', ma_tbao='TK',
                              so_thong_bao='238642/0111/2025/TB-TĐT',
                              account_key=account_fingerprint('synthetic-personal'))
            path = store.save(record, NOTICE_XML)
            self.assertIsNotNone(path)
            self.assertEqual(path.suffix, '.xml')
            again = ThongBao(message_id='85328477', ma_tbao='TK',
                             so_thong_bao='238642/0111/2025/TB-TĐT',
                             account_key=account_fingerprint('synthetic-personal'))
            self.assertEqual(store.find_existing(again), path)


class PersonalLoginTests(unittest.TestCase):
    def test_two_step_login_sets_session_and_home_page(self):
        settings = personal_settings()
        pages = iter([
            FakeResponse('<script>window.location.href="/ICanhan/Request?dse_sessionId=s1&dse_pageId=2";</script>'),
            FakeResponse('<form id="goProcForm" action="/ICanhan/Request"><input name="dse_sessionId" value="s1"><input name="dse_operationName" value="retailIndexProc"><input name="dse_nextEventName" value="start"></form>', url='https://canhan.gdt.gov.vn/ICanhan/Request'),
            FakeResponse(LOGIN_FORM, url='https://canhan.gdt.gov.vn/ICanhan/Request'),
        ])
        login_posts = []

        def handler(method, path, kwargs):
            if path.endswith('/servlet/ImageServlet'):
                return FakeResponse(content=b'\x89PNG' + b'0' * 200,
                                    headers={'content-type': 'image/png'})
            if method == 'GET':
                return next(pages, FakeResponse(HOME_HTML))
            data = kwargs.get('data') or {}
            login_posts.append(data)
            if data.get('_userName'):
                return FakeResponse(PASSWORD_FORM, url='https://canhan.gdt.gov.vn/ICanhan/Request')
            if data.get('_password'):
                return FakeResponse(HOME_HTML, url='https://canhan.gdt.gov.vn/ICanhan/Request')
            if data.get('dse_operationName') == 'retailUserLoginProc':
                return FakeResponse(LOGIN_FORM, url='https://canhan.gdt.gov.vn/ICanhan/Request')
            return FakeResponse(HOME_HTML, url='https://canhan.gdt.gov.vn/ICanhan/Request')

        from gdt_tax.legacy_session import LegacySessionState
        session = LegacySessionState()
        portal = CanhanPortal(FakeHttp(handler), StubCaptcha('abc12'), settings,
                              session_state=session)
        portal.login()
        self.assertTrue(session.authenticated)
        self.assertEqual(session.dse_session_id, 's1')
        self.assertEqual(session.home_page_id, '9')
        self.assertTrue(any(data.get('_userName') == 'synthetic-personal' for data in login_posts))
        self.assertTrue(any(data.get('_password') == 'fixture' for data in login_posts))


class PersonalOriginTests(unittest.TestCase):
    def test_canhan_origin_is_reviewed_but_unknown_origin_is_rejected(self):
        from gdt_tax.errors import NetworkError
        from gdt_tax.http_policy import OriginPolicy

        policy = OriginPolicy()
        policy.validate('https://canhan.gdt.gov.vn/ICanhan/Request')
        with self.assertRaises(NetworkError):
            policy.validate('https://example.invalid/ICanhan/Request')


class PersonalConfigurationTests(unittest.TestCase):
    def test_personal_uses_canhan_for_all_dates(self):
        from desktop.services import RunConfig
        from desktop.settings_store import Preferences

        config = RunConfig('tax', Path('/tmp/personal-account-test'), username='synthetic',
                           password='fixture', account_type='CN', preferences=Preferences())
        settings = config.settings()
        self.assertEqual(settings.account_type, 'CN')
        self.assertTrue(settings.legacy_etax)
        self.assertFalse(settings.dvc_enabled)
        self.assertEqual(settings.etax_cutoff.year, 2100)
        self.assertTrue(settings.periods())
        self.assertTrue(all(period.source == 'ETAX_LEGACY' for period in settings.periods()))

    def test_personal_output_and_credentials_stay_separate(self):
        from desktop.account_store import target_name
        from desktop.state import job_output

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertNotEqual(job_output(root, 'synthetic', 'tax'),
                                job_output(root, 'synthetic', 'tax', 'CN'))
        self.assertNotEqual(target_name('synthetic'), target_name('synthetic', 'CN'))


class PersonalSessionTests(unittest.TestCase):
    def test_personal_tax_uses_canhan_portal_and_skips_dvc(self):
        from desktop.services import JobResult, RunConfig
        from desktop.sessions import ETaxSessionManager

        with tempfile.TemporaryDirectory() as directory:
            manager = ETaxSessionManager()
            self.addCleanup(manager.close)
            manager.set_account_type('CN')
            config = RunConfig('tax', Path(directory), username='synthetic',
                               password='fixture', account_type='CN')
            with patch('desktop.sessions.CanhanPortal') as portal_class, \
                    patch('desktop.sessions.run_online',
                          return_value=JobResult('SUCCESS', 'Thành công', config.output)) as run:
                result = manager.execute(config, Mock(), StubCaptcha(), None)
            self.assertEqual(result.state, 'SUCCESS')
            portal_class.return_value.login.assert_called_once()
            self.assertIs(run.call_args.kwargs['http'], manager.http)
            self.assertFalse(run.call_args.kwargs['authenticate'])
            factory = run.call_args.kwargs['portal_factory']
            self.assertEqual(factory(), {'ETAX_LEGACY': portal_class.return_value})

    def test_personal_notice_uses_the_same_canhan_session(self):
        from desktop.services import JobResult, RunConfig
        from desktop.sessions import ETaxSessionManager

        with tempfile.TemporaryDirectory() as directory:
            manager = ETaxSessionManager()
            self.addCleanup(manager.close)
            manager.set_account_type('CN')
            config = RunConfig('notice', Path(directory), username='synthetic',
                               password='fixture', account_type='CN')
            with patch('desktop.sessions.CanhanPortal') as portal_class, \
                    patch('desktop.sessions.run_online',
                          return_value=JobResult('SUCCESS', 'Thành công', config.output)) as run:
                result = manager.execute(config, Mock(), StubCaptcha(), None)
            self.assertEqual(result.state, 'SUCCESS')
            self.assertIs(run.call_args.kwargs['portal_factory'](), portal_class.return_value)

    def test_personal_gnt_is_reported_unsupported_without_network(self):
        from desktop.services import RunConfig
        from desktop.sessions import ETaxSessionManager

        with tempfile.TemporaryDirectory() as directory:
            manager = ETaxSessionManager()
            self.addCleanup(manager.close)
            manager.set_account_type('CN')
            config = RunConfig('gnt', Path(directory), username='synthetic',
                               password='fixture', account_type='CN')
            result = manager.execute(config, Mock(), StubCaptcha(), None)
        self.assertEqual(result.state, 'ERROR')
        self.assertEqual(result.error_code, 'UNSUPPORTED_ACCOUNT_FLOW')
        self.assertIn('canhan.gdt.gov.vn', result.message)


if __name__ == '__main__':
    unittest.main()
