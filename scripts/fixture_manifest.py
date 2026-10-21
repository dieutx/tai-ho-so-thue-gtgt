"""Record fixture hashes without inventing capture/sanitization provenance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'
HTML = {
    'etax_results.html': ('ETAX', 2, 'PARSED'),
    'etax_legacy_results.html': ('ETAX_LEGACY', 2, 'PARSED'),
    'etax_legacy_empty.html': ('ETAX_LEGACY', 0, 'EMPTY_CONFIRMED'),
    'etax_legacy_notices.html': ('ETAX_LEGACY', 2, 'PARSED'),
    'dvc_results_page1.html': ('DVC', 2, 'PARSED'),
    # Historical empty tbody has pagination but no reviewed empty evidence.
    'dvc_results_page2.html': ('DVC', 0, 'SCHEMA_CHANGED'),
    'gnt_results_page1.html': ('GNT', 2, 'PARSED'),
    'gnt_results_page2.html': ('GNT', 1, 'PARSED'),
    'tb_results_page1.html': ('TB', 2, 'PARSED'),
    'tb_results_page2.html': ('TB', 1, 'PARSED'),
}


def canonical_bytes(path):
    data = path.read_bytes()
    return data.replace(b'\r\n', b'\n') if path.suffix in {'.html', '.xml', '.json'} else data


def build():
    rows = []
    for path in sorted(FIXTURES.rglob('*')):
        if not path.is_file() or path == FIXTURES / 'manifest.json':
            continue
        source, count, outcome = HTML.get(path.name, ('OFFLINE', None, 'GOLDEN_OR_BINARY'))
        synthetic = path.relative_to(FIXTURES).parts[0] == 'auth' or path.name in {'tb_notice.pdf', 'sample_captcha.png'}
        rows.append({'path': path.relative_to(FIXTURES).as_posix(), 'source': source,
            'operation': 'attachment_list' if path.name == 'etax_legacy_notices.html' else 'search' if path.suffix == '.html' else 'auth_matrix' if path.parent.name == 'auth' else 'offline_fixture',
            'provenance': 'synthetic' if synthetic else 'inherited_unverified',
            'sanitized_at': '2026-10-21' if synthetic else None,
            'adapter_version': 'auth-v1' if path.parent.name == 'auth' else 'portal-table-v1',
            'content_kind': path.suffix.lstrip('.'), 'expected_rows': count, 'expected_outcome': outcome,
            'canonical_sha256': hashlib.sha256(canonical_bytes(path)).hexdigest(),
            'sanitization': 'constructed fixture, no live capture' if synthetic else
                'Historical repository fixture; original capture and anonymization unverified. Do not distribute as sanitized live evidence.'})
    return {'schema_version': 1, 'hash_policy': 'CRLF-to-LF for html/xml/json; binary unchanged', 'fixtures': rows}


if __name__ == '__main__':
    (FIXTURES / 'manifest.json').write_text(json.dumps(build(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
