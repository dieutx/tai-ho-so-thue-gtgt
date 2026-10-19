"""Reproducible byte inventory for CArchive and actual onedir payload."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from importlib.metadata import distributions
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--folder', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    archive = CArchiveReader(str(args.exe))
    entries = [{'path': k, 'compressed_bytes': v[1], 'bytes': v[2], 'type': v[4]}
               for k, v in archive.toc.items()]
    groups: dict[str, int] = defaultdict(int)
    for row in entries:
        groups[row['path'].replace('\\', '/').split('/')[0]] += row['bytes']
    payload = {'exe_bytes': args.exe.stat().st_size, 'entry_count': len(entries),
               'archive_uncompressed_bytes': sum(r['bytes'] for r in entries),
               'top30_archive': sorted(entries, key=lambda r: r['bytes'], reverse=True)[:30],
               'groups': sorted(groups.items(), key=lambda x: x[1], reverse=True),
               'packages': sorted([(d.metadata['Name'], d.version) for d in distributions()])}
    if args.folder:
        files = [{'path': str(p.relative_to(args.folder)), 'bytes': p.stat().st_size}
                 for p in args.folder.rglob('*') if p.is_file()]
        payload.update(onedir_bytes=sum(r['bytes'] for r in files), onedir_files=len(files),
                       top30_onedir=sorted(files, key=lambda r: r['bytes'], reverse=True)[:30])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in payload.items() if k.endswith('_bytes') or k.endswith('_count')}))


if __name__ == '__main__':
    main()
