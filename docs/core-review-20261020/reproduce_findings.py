"""Offline observations of baseline 559892f; these are NOT regression tests.

Run from any working directory with the project's runtime Python. No network,
credentials, CAPTCHA, real tax files, or edits to production modules are used.
After a fix, an observation may change: promote that case to a regression test.
"""
# Imports below follow the repository path setup so this file also runs directly.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bs4 import BeautifulSoup

from gdt_tax.config import Settings
from gdt_tax.export import build_rows, build_workbook, write_csv
from gdt_tax.gnt.portal import is_gnt_xml
from gdt_tax.inventory import scan_directory
from gdt_tax.models import CaseRecord, PageResult
from gdt_tax.parser.cli import main as parse_main
from gdt_tax.parser.extract import extract_declaration
from gdt_tax.parser.registry import FormMapping, MappingRegistry, load_registry
from gdt_tax.parser.xml_reader import normalize_number, parse_xml
from gdt_tax.parsing import parse_records
from gdt_tax.pipeline import Pipeline
from gdt_tax.portals.etax_legacy import _form_fields, _total_pages
from gdt_tax.tb.portal import is_tb_pdf
from gdt_tax.traffic import describe_body, mask_headers
from tests.support import fixture
from tests.test_http import StubResponse, make_client
from tests.test_parser import RETURN_XML


def observe() -> list[dict]:
    observations = []

    def add(case, ticket, observation):
        observations.append({'case': case, 'ticket': ticket, 'observation': observation})

    html = fixture('etax_legacy_results.html')
    changed = html.replace('downloadTkhai(', 'downloadDeclaration(')
    add('R01', 'CORE-01', {'rows_before': len(parse_records(html, 'ETAX_LEGACY')),
                          'rows_after_action_rename': len(parse_records(changed, 'ETAX_LEGACY')),
                          'reported_total_pages': _total_pages(changed)})

    soup = BeautifulSoup(fixture('etax_results.html'), 'html.parser')
    for row in soup.select('tbody tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) >= 10:
            date, office = cells[7].get_text(), cells[8].get_text()
            cells[7].clear()
            cells[7].append(office)
            cells[8].clear()
            cells[8].append(date)
    before = parse_records(fixture('etax_results.html'), 'ETAX')
    after = parse_records(str(soup), 'ETAX')
    add('R02', 'CORE-02', {'records_retained': len(after) == len(before),
                          'date_field_now_contains_office': after[0].ngay_nop == before[0].noi_nop})

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        settings = Settings.from_env(environ={}, env_file=None, username='fixture', password='fixture',
                                     from_date='30/06/2025', to_date='01/07/2025',
                                     download_dir=root, dvc_enabled=True, dry_run=True,
                                     pause_between_records=0, pause_between_pages=0)
        portals = {s: SimpleNamespace(source=s, search=lambda period, page: PageResult(
            [CaseRecord('shared-fixture-id', period.source)], 1, 200))
            for s in ['ETAX_LEGACY', 'DVC']}
        pipeline = Pipeline(settings, SimpleNamespace(), SimpleNamespace(),
                            portal_factory=lambda *_: portals, persist_metadata=False)
        with patch('gdt_tax.pipeline.login', return_value=True), patch('gdt_tax.pipeline.open_landing', return_value=''):
            summary = pipeline.run()
        add('R03', 'CORE-03', {'source_records_returned': 2, 'records_retained': len(pipeline.records),
                              'search_marked_complete': summary.search_complete})

        manifest = {'containers': [{'members': [{'artifact_id': 'new-artifact', 'sha256': 'new-sha'}]}]}
        parsed = {'declarations': [{'artifact_id': 'old-artifact', 'source_sha256': 'old-sha',
                                    'form_code': '=1+1', 'status': 'NEED_MAPPING',
                                    'error': 'fixture-error', 'warnings': ['fixture-warning'],
                                    'mapping_version': 'fixture-v1',
                                    'indicators': [{'code': 'ct1', 'value': '-100', 'raw_value': '-100'}]}]}
        rows = build_rows(manifest, parsed, None)
        add('R04', 'CORE-04', {'old_artifact_exported_against_new_manifest': bool(rows),
                              'exported_source_sha': rows[0]['source_sha256']})
        workbook = build_workbook(rows, manifest, parsed, None)
        add('R05', 'CORE-05', {'index_form_code_type': workbook['01_RETURN_INDEX']['C2'].data_type,
                              'indicator_form_code_type': workbook['05_INDICATORS']['C2'].data_type,
                              'unmapped_form_code_type': workbook['07_UNMAPPED_FORMS']['B2'].data_type})
        write_csv(root/'fixture.csv', rows)
        add('R06', 'CORE-05', {'csv_retains_formula_prefix': '=1+1' in (root/'fixture.csv').read_text(encoding='utf-8-sig')})
        add('R07', 'CORE-06', {'normalized_number_cell_type': workbook['05_INDICATORS']['L2'].data_type,
                              'normalized_number_cell_value': workbook['05_INDICATORS']['L2'].value,
                              'error_preserved_in_row': 'error' in rows[0],
                              'mapping_version_preserved_in_row': 'mapping_version' in rows[0]})
        workbook.close()

        registry = MappingRegistry()
        registry.add(FormMapping('first', '1', 'fixture', '1'))
        registry.add(FormMapping('second', '1', 'fixture', '1'))
        add('R08', 'CORE-09', {'same_key_mapping_count': len(registry),
                              'silently_selected_mapping': registry.lookup('fixture', '1').mapping_id})
        mapping_dir = root/'mapping'
        mapping_dir.mkdir()
        (mapping_dir/'bad.json').write_text(json.dumps({'mapping_id': 'bad', 'mapping_version': '1',
            'form_code': 'fixture', 'fields': ['not-an-object']}), encoding='utf8')
        error_type = None
        try:
            load_registry(mapping_dir)
        except Exception as error:
            error_type = type(error).__name__
        add('R09', 'CORE-09', {'malformed_mapping_exception': error_type})

        for folder, content in [('a', b'<a/>'), ('b', b'<b/>')]:
            (root/folder).mkdir()
            (root/folder/'same.xml').write_bytes(content)
            os.utime(root/folder/'same.xml', (1000000000, 1000000000))
        first = scan_directory(root/'a')
        second = scan_directory(root/'b', cache={c.rel_path: c for c in first.containers})
        add('R10', 'CORE-10', {'actual_second_xml_root': 'b',
                              'cached_second_xml_root': second.containers[0].members[0].xml.root_element})

        (root/'bad.xml').write_bytes(b'<broken>')
        (root/'manifest.json').write_text(json.dumps({'containers': [{'rel_path': 'bad.xml', 'format': 'xml',
            'members': [{'format': 'xml', 'status': 'ok', 'member_name': 'bad.xml', 'artifact_id': 'bad',
                         'sha256': hashlib.sha256(b'<broken>').hexdigest()}]}]}), encoding='utf8')
        exit_code = parse_main([str(root), '--manifest', str(root/'manifest.json')])
        add('R11', 'CORE-11', {'parse_exit_code_with_only_errors': exit_code,
                               'declaration_status': json.loads((root/'parsed_declarations.json').read_text())['declarations'][0]['status']})

    prefixed = RETURN_XML.decode().replace('xmlns=', 'xmlns:p=')
    prefixed = re.sub(r'<(/?)([A-Za-z][A-Za-z0-9_]*)(?=[\s>])', r'<\1p:\2', prefixed).encode()
    add('R12', 'CORE-07', {'default_namespace_form_code': extract_declaration(RETURN_XML).form_code,
                           'equivalent_prefixed_namespace_form_code': extract_declaration(prefixed).form_code})
    add('R13', 'CORE-08', {value: normalize_number(value) for value in ['0.125', '1.234', '12.34.56']})
    deep = b'<r>'*110 + b'</r>'*110
    add('R14', 'CORE-12', {'declared_depth_limit': 100, 'depth_110_accepted_by_parser': parse_xml(deep) is not None})
    add('R15', 'CORE-13', {'unrelated_xml_accepted_as_gnt': is_gnt_xml(b'<status><message>failed</message></status>'),
                           'truncated_pdf_accepted': is_tb_pdf(b'%PDF-1.7\ntruncated')})
    action, _ = _form_fields('<form id="loginForm" action="https://untrusted.example/collect"></form>', 'loginForm')
    add('R16', 'CORE-14', {'external_form_action_accepted': action == 'https://untrusted.example/collect'})
    client, _ = make_client([])
    add('R17', 'CORE-15', {'infinite_retry_after_accepted': client._retry_delay(StubResponse(429, {'Retry-After': 'inf'})) == float('inf')})
    add('R18', 'CORE-16', {'json_string_secret_retained': 'fixture-secret' in describe_body('{"password":"fixture-secret"}'),
                           'referer_session_retained': 'fixture-session' in mask_headers({'Referer': 'https://fixture.test/?dse_sessionId=fixture-session'})['Referer']})
    return observations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Write synthetic observations to JSON')
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Review probes must stay offline')):
        observations = observe()
    payload = {'baseline_commit': '559892f1ff22f3e68d2fbea7be0608fd0ac597c9',
               'offline': True, 'real_credentials_or_tax_data_used': False,
               'case_count': len(observations), 'observations': observations}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf8')
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
