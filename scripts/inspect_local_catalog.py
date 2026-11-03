"""Read-only SQLite counts/integrity; never prints tax metadata or account IDs."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    with closing(sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        result = {'schema_version': db.execute('PRAGMA user_version').fetchone()[0],
                  'integrity': db.execute('PRAGMA integrity_check').fetchone()[0],
                  'foreign_key_violations': len(db.execute('PRAGMA foreign_key_check').fetchall()),
                  'documents': dict(db.execute('SELECT mode,COUNT(*) FROM documents GROUP BY mode')),
                  'artifacts': db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],
                  'quarantine': db.execute('SELECT COUNT(*) FROM quarantine').fetchone()[0],
                  'sync_states': dict(db.execute('SELECT state,COUNT(*) FROM sync_runs GROUP BY state'))}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
