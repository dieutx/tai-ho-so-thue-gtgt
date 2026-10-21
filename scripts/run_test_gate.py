"""Offline CI gate with explicit skip evidence and required Full desktop capabilities."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gate_payload(result, profile, source_sha):
    skipped = [{'test': test.id(), 'reason': reason} for test, reason in result.skipped]
    required_skips = [item for item in skipped if 'Desktop' in item['test'] or
                      'Qt' in item['reason'] or 'DdddOcrBackendTests' in item['test']]
    return {'schema_version': 1, 'profile': profile, 'source_sha': source_sha,
            'python': platform.python_version(), 'system': platform.system(),
            'tests': result.testsRun, 'skipped': skipped,
            'failures': [test.id() for test, _ in result.failures + result.errors],
            'pass': result.wasSuccessful() and (profile == 'minimal' or not required_skips)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['minimal', 'desktop'], required=True)
    args = parser.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if args.profile == 'desktop':
        for module in ('PySide6', 'ddddocr', 'onnxruntime'):
            if importlib.util.find_spec(module) is None:
                raise SystemExit('Required desktop capability missing: ' + module)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    payload = gate_payload(result, args.profile, sha)
    target = ROOT / '.cache/ci' / (args.profile + '.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(f'GATE: {args.profile} pass={payload["pass"]} tests={payload["tests"]} skipped={len(payload["skipped"])}')
    return 0 if payload['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
