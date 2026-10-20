"""Recover derived reports from the canonical catalog without network access."""
from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from .catalog import catalog_lock, reports_current
from .gnt.models import GiayNopTien
from .gnt.storage import write_gnt_metadata
from .identity import key_from_row
from .integrity import read_bounded
from .models import CaseRecord
from .storage import write_metadata
from .tb.models import ThongBao
from .tb.storage import write_tb_metadata


def rebuild(catalog: Path, kind: str):
    record_type, writer, canonical = {
        'DECLARATION': (CaseRecord, write_metadata, 'danh_sach_ho_so.json'),
        'GNT': (GiayNopTien, write_gnt_metadata, 'danh_sach_giay_nop_tien.json'),
        'NOTICE': (ThongBao, write_tb_metadata, 'danh_sach_thong_bao.json'),
    }[kind]
    if catalog.name != canonical:
        raise ValueError('REBUILD_CANONICAL_CATALOG_REQUIRED')
    with catalog_lock(catalog.parent):
        rows = json.loads(read_bounded(catalog, 128 * 1024 * 1024))
        if not isinstance(rows, list) or not rows:
            raise ValueError('REBUILD_NONEMPTY_CATALOG_REQUIRED')
        allowed = {field.name for field in fields(record_type)}
        records = []
        for row in rows:
            key = key_from_row(row, kind)
            values = {name: value for name, value in row.items() if name in allowed}
            values['account_key'] = key.account_key
            if kind == 'DECLARATION':
                values['nguon'] = key.source
            records.append(record_type(**values))
        # Already hold the same OS lock; invoke only the undecorated writer.
        writer.__wrapped__(catalog.parent, records)
        return reports_current(catalog)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Dựng lại CSV/XLSX từ JSON đã commit, không dùng mạng')
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--kind', choices=('DECLARATION', 'GNT', 'NOTICE'), required=True)
    args = parser.parse_args(argv)
    return 0 if rebuild(args.catalog, args.kind) else 1


if __name__ == '__main__':
    raise SystemExit(main())
