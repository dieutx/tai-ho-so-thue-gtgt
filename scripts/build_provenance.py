"""Write a credential-free release receipt after source/frozen/audit gates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def build_receipt(root: Path):
    info = json.loads((root / 'desktop/resources/release.json').read_text(encoding='utf-8'))
    gate = json.loads((root / '.cache/ci/desktop.json').read_text(encoding='utf-8'))
    audit = json.loads((root / '.cache/bundle-audit.json').read_text(encoding='utf-8'))
    if not gate.get('pass') or not audit.get('pass') or gate['source_sha'] != info['source_sha']:
        raise ValueError('BUILD_PROVENANCE_GATE_FAILED')
    smoke_path = Path((root / '.cache/last-smoke-path.txt').read_text(encoding='utf-8-sig').strip())
    if not smoke_path.resolve().is_relative_to((root / '.cache').resolve()):
        raise ValueError('BUILD_SMOKE_SCOPE_INVALID')
    smoke = [json.loads((smoke_path / f'report-{index}.json').read_text(encoding='utf-8')) for index in (1, 2)]
    if not all(item.get('pass') and item.get('frozen') and item.get('source_sha') == info['source_sha'] for item in smoke):
        raise ValueError('BUILD_FROZEN_GATE_FAILED')
    for name, digest in info['dependency_inventory_sha256'].items():
        if Path(name).name != name or sha256(root / 'packaging' / name) != digest:
            raise ValueError('BUILD_DEPENDENCY_PROVENANCE_CHANGED')
    exe = root / 'dist/TaiHoSoThue-Windows.exe'
    checksum = root / 'dist/SHA256SUMS.txt'
    checksum.write_text(sha256(exe) + '  ' + exe.name + '\n', encoding='ascii')
    assets = {path.name: {'sha256': sha256(path), 'bytes': path.stat().st_size} for path in (exe, checksum)}
    receipt = {**info, 'schema_version': 1, 'tag': 'desktop-v' + info['version'], 'assets': assets,
               'source_gate_sha256': sha256(root / '.cache/ci/desktop.json'),
               'bundle_audit_sha256': sha256(root / '.cache/bundle-audit.json'),
               'frozen_reports_sha256': [sha256(smoke_path / f'report-{index}.json') for index in (1, 2)]}
    (root / 'dist/release-manifest.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return receipt


if __name__ == '__main__':
    build_receipt(ROOT)
