"""Controlled Windows/CPython inventory, exact transitive pins and metadata hashes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalized(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def inventory():
    packages = {}
    for dist in metadata.distributions():
        name = normalized(dist.metadata['Name'])
        if name in {'tai-ho-so-thue-gtgt', 'pip'}:
            continue
        packages[name] = {'name': name, 'version': dist.version,
            'metadata_sha256': hashlib.sha256((dist.read_text('METADATA') or '').encode()).hexdigest(),
            'wheel_sha256': hashlib.sha256((dist.read_text('WHEEL') or '').encode()).hexdigest()}
    return {'schema_version': 1, 'python': '.'.join(platform.python_version_tuple()[:2]),
            'implementation': platform.python_implementation(), 'system': platform.system(),
            'bits': struct.calcsize('P') * 8, 'packages': [packages[key] for key in sorted(packages)]}


def verify(expected, actual):
    if expected != actual:
        raise ValueError('DEPENDENCY_INVENTORY_MISMATCH: rebuild from the reviewed platform lock or review the dependency change')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['capture', 'verify'])
    parser.add_argument('--profile', choices=['runtime', 'tools'], required=True)
    args = parser.parse_args()
    current = inventory()
    if (current['python'], current['implementation'], current['system'], current['bits']) != ('3.11', 'CPython', 'Windows', 64):
        raise SystemExit('Inventory requires CPython 3.11 Windows x64')
    stem = 'desktop' if args.profile == 'runtime' else 'build-tools'
    path = ROOT / 'packaging' / f'{stem}-windows-py311.inventory.json'
    if args.action == 'capture':
        path.write_text(json.dumps(current, indent=2) + '\n', encoding='utf-8')
        (ROOT / f'requirements-{stem}-windows-py311.lock').write_text(
            '# Reviewed CPython 3.11 Windows x64 inventory; install with --no-deps, then pip check.\n' +
            '\n'.join(p['name'] + '==' + p['version'] for p in current['packages']) + '\n', encoding='utf-8')
    else:
        verify(json.loads(path.read_text(encoding='utf-8')), current)
    print('DEPENDENCY_INVENTORY_OK: ' + args.profile)


if __name__ == '__main__':
    main()
