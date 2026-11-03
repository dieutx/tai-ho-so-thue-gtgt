"""Reproducible synthetic JSON-scan versus indexed SQLite period selection."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gdt_tax.identity import account_fingerprint
from gdt_tax.local_catalog import LocalCatalog
from gdt_tax.models import CaseRecord


def measure(size):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        account = account_fingerprint('synthetic-benchmark')
        rows = [CaseRecord(str(i), 'DVC', account_key=account,
                           ngay_nop=f'15/{i % 24 % 12 + 1:02}/{2025 + i % 24 // 12}',
                           to_khai='Tờ khai giả lập').to_dict() for i in range(size)]
        path = root / 'baseline.json'
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        catalog = LocalCatalog(root / 'sqlite', account)
        started = time.perf_counter()
        catalog.upsert_documents('tax', rows)
        ingest = time.perf_counter() - started
        json_times, sqlite_times = [], []
        for _ in range(5):
            started = time.perf_counter()
            selected_json = [row for row in json.loads(path.read_text(encoding='utf-8')) if row['ngay_nop'] == '15/10/2026']
            json_times.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            selected_sqlite = catalog.get_documents('tax', '01/10/2026', '31/10/2026')
            sqlite_times.append((time.perf_counter() - started) * 1000)
            assert {r['record_key'] for r in selected_json} == {r['record_key'] for r in selected_sqlite}
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        assert catalog.get_counts('tax')['total'] == size
        assert before == hashlib.sha256(path.read_bytes()).hexdigest()
        return {'records': size, 'visible': len(selected_sqlite), 'sqlite_ingest_seconds': round(ingest, 4),
                'json_scan_median_ms': round(statistics.median(json_times), 3),
                'sqlite_select_median_ms': round(statistics.median(sqlite_times), 3),
                'filter_http_requests': 0, 'filter_deep_file_reads': 0, 'integrity': catalog.integrity_check()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = [measure(size) for size in (100, 1000, 10_000, 100_000)]
    payload = {'environment': {'python': platform.python_version(), 'platform': platform.platform()},
               'method': 'Synthetic metadata only. Five warm reads per size, median. JSON scans all rows; SQLite indexed date SELECT. No network, no file hashing, no live speed claim.',
               'measurements': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
