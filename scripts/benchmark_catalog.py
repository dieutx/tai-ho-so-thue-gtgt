"""Synthetic persistence measurements; large baseline operation counts are modeled.

Run from repo: python scripts/benchmark_catalog.py --output benchmark.json
Real legacy per-record workbook saves are measured at 100 records; checkpointed
runs are measured at 100/1000/5000. Never labels an extrapolation as elapsed time.
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gdt_tax import storage
from gdt_tax.catalog import CatalogCheckpoint
from gdt_tax.models import CaseRecord


def measure(size, *, legacy=False):
    metrics = {'records': size, 'mode': 'per_record_reports' if legacy else 'checkpointed',
               'workbook_saves': 0, 'bytes_written': 0, 'catalog_commits': 0}
    original_atomic, original_excel = storage._atomic_write, storage.write_excel_report
    def atomic(path, data):
        metrics['bytes_written'] += len(data)
        metrics['catalog_commits'] += int(Path(path).name == 'danh_sach_ho_so.json')
        return original_atomic(path, data)
    def excel(path, rows):
        metrics['workbook_saves'] += 1
        return original_excel(path, rows)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as temporary, patch.object(storage, '_atomic_write', atomic), \
            patch.object(storage, 'write_excel_report', excel):
        records = {}
        checkpoint = CatalogCheckpoint(storage.write_metadata, temporary)
        for index in range(size):
            record = CaseRecord(f'synthetic-{index:05}', 'DVC', to_khai='Synthetic benchmark')
            records[record.record_key] = record
            if legacy:
                storage.write_metadata(temporary, records)
            else:
                checkpoint.persist(records)
        if not legacy:
            checkpoint.persist(records, materialize=True)
    metrics['elapsed_seconds'] = round(time.perf_counter() - started, 4)
    return metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    results = [measure(100, legacy=True)]
    results.extend(measure(size) for size in (100, 1000, 5000))
    payload = {'environment': {'platform': platform.platform(), 'python': platform.python_version()},
               'method': 'real fsync/atomic writes and real openpyxl saves; legacy policy simulated with current writer at N=100',
               'large_baseline_operation_counts_only': [
                   {'records': size, 'workbook_saves': size, 'catalog_commits': size,
                    'rows_materialized': size * (size + 1) // 2} for size in (100, 1000, 5000)],
               'measurements': results}
    args.output.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps(payload, indent=2))


if __name__ == '__main__':
    main()
