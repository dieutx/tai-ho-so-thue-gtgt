"""Measure the same frozen offline+OCR workflow before/after, with real EXEs."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--after', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    fixtures = Path('tests/fixtures').resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, exe in [('before', args.before), ('after', args.after)]:
        samples = []
        reports = []
        for index in range(3):
            directory = (args.output / f'{label}-{index + 1}').resolve()
            directory.mkdir(exist_ok=True)
            report = directory / 'report.json'
            started = time.perf_counter()
            subprocess.run([str(exe.resolve()), '--self-test', str(fixtures), '--test-output',
                            str(directory / 'output'), '--test-report', str(report)],
                           check=True, timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                           env=dict(os.environ, QT_QPA_PLATFORM='windows'))
            samples.append(time.perf_counter() - started)
            payload = json.loads(report.read_text(encoding='utf-8'))
            assert payload['pass'] and payload['frozen'] and payload['ocr_offline'], payload
            reports.append({key: payload[key] for key in ['state', 'declarations', 'mapped']})
        results[label] = {'seconds': samples, 'median_seconds': statistics.median(samples), 'reports': reports}
    assert results['before']['reports'] == results['after']['reports'], results
    results['method'] = '3 fresh processes each; frozen offline all stages + OCR; includes onefile extraction/startup; same fixtures, no network; OS caches not flushed'
    (args.output / 'workflow.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
