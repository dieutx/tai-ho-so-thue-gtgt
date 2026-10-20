"""Supplementary offline observations; requires an explicit source snapshot.

This concerns uncommitted DVC changes, not baseline commit 559892f.
"""
# Source selection must precede imports from the checkout under review.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import logging
import socket
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-root', type=Path, required=True)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
source_root = args.source_root.resolve()
sys.path.insert(0, str(source_root))

from gdt_tax.config import Settings
from gdt_tax.constants import DVC_NOTICE_DOWNLOAD
from gdt_tax.dvc_notices import DvcNotice, NoticeFile, NoticeStore, decode_notice_response
from gdt_tax.pipeline import Pipeline
from tests.support import FakeHttp, FakeResponse, StubCaptcha, route_of
from tests.test_pipeline import dvc_search, make_handler

paths = ['gdt_tax/dvc_notices.py', 'gdt_tax/pipeline.py', 'gdt_tax/portals/dvc.py',
         'gdt_tax/portals/base.py', 'desktop/main.py', 'tests/test_dvc_notices.py']
sources = []
for path in paths:
    data = (source_root/path).read_bytes()
    tree = ast.parse(data.decode('utf-8-sig'))
    sources.append({'path': path, 'sha256': hashlib.sha256(data).hexdigest(),
                    'definitions': {node.name: node.lineno for node in ast.walk(tree)
                                    if isinstance(node, (ast.ClassDef, ast.FunctionDef))}})

observations = []
logging.disable(logging.CRITICAL)
with patch.object(socket.socket, 'connect', side_effect=AssertionError('offline only')):
    response = FakeResponse(json_payload={'fileName': 'fixture.xml', 'fileType': 'xml',
        'content': base64.b64encode(b'<html><body>fixture error</body></html>').decode()})
    decoded = decode_notice_response(response)
    observations.append({'case':'W01','related_tickets':['CORE-13','CORE-15'],
        'html_error_payload_accepted_as_notice':decoded is not None,
        'declared_extension':decoded.extension if decoded else None})
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        store = NoticeStore(root/'notices')
        notice = DvcNotice('fixture-notice-id', title='fixture', is_tdt=False)
        saved = store.save('fixture-case', notice, NoticeFile('fixture.xml', b'x', 'xml'))
        observations.append({'case':'W02','related_tickets':['CORE-13'],
            'one_byte_xml_saved':saved is not None,
            'one_byte_xml_reused':store.find_existing('fixture-case', notice.id) is not None})
        distinct_source_notice = DvcNotice(notice.id, title='other source', is_tdt=True)
        observations.append({'case':'W03','related_tickets':['CORE-03'],
            'different_source_notice_reuses_same_path':store.find_existing('fixture-case', distinct_source_notice.id) == saved})

        detail = ('<input name="_csrf" value="fixture-token"><div id="modalThongBao">'
                  '<div class="row"><div class="col-md-9"><div class="fw-bold">fixture</div></div>'
                  '<a data-id="fixture-notice-id" onclick="downloadThongBao(this)">download</a></div></div>')
        base = make_handler(search=dvc_search)
        failed_posts = []
        def handler(method, path, kwargs):
            route = route_of(path)
            if route.startswith('/tchs/files/detail/'):
                return FakeResponse(detail)
            if route == DVC_NOTICE_DOWNLOAD:
                failed_posts.append(True)
                return FakeResponse('fixture server error', status_code=500)
            return base(method, path, kwargs)
        settings = Settings(username='fixture', password='fixture',
            from_date=date(2026,1,1), to_date=date(2026,1,31), download_dir=root/'pipeline',
            login_attempts=1, search_attempts=1, pause_between_records=0,
            pause_between_pages=0, dvc_enabled=True, legacy_etax=False)
        pipeline = Pipeline(settings, FakeHttp(handler), StubCaptcha(), sleep=lambda _:None)
        summary = pipeline.run()
        observations.append({'case':'W04','related_tickets':['CORE-01','CORE-17'],
            'failed_notice_download_requests':len(failed_posts),
            'primary_documents_downloaded':summary.downloaded,
            'primary_summary_complete':summary.complete,
            'notice_failures_in_record_errors':bool(pipeline.record_errors),
            'notice_failure_field_in_summary':any('notice' in key or 'attachment' in key for key in vars(summary))})

assert all(hashlib.sha256((source_root/s['path']).read_bytes()).hexdigest() == s['sha256'] for s in sources)
payload = {'scope':'supplementary uncommitted source snapshot; not baseline commit',
           'offline':True,'real_credentials_or_tax_data_used':False,
           'case_count':len(observations),'sources':sources,'observations':observations}
if args.output:
    args.output.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
print(json.dumps({'case_count':len(observations),'observations':observations},indent=2))
