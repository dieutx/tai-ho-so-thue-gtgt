"""Explicit, reversible catalog-only migration. Never claims legacy ownership."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .identity import IDENTITY_VERSION, IdentityError, key_from_row
from .integrity import read_bounded
from .storage import _atomic_write

LIMIT = 32 * 1024 * 1024
VERSION = "identity-migration-v1"


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def migrate(catalog: Path, kind: str, *, apply: bool = False, rollback: bool = False) -> dict:
    """Preview by default; repeat/rollback verify exact original and migrated bytes."""
    catalog = Path(catalog)
    data = read_bounded(catalog, LIMIT)
    journal = catalog.with_name(".gdt-" + catalog.name + ".identity-migration.json")
    backup = catalog.with_name(".gdt-" + catalog.name + ".identity-original")
    if journal.exists():
        entry = json.loads(read_bounded(journal, 4096))
        if (not isinstance(entry, dict) or entry.get("schema_version") != VERSION
                or entry.get("catalog") != catalog.name or entry.get("kind") != kind):
            raise IdentityError("MIGRATION_JOURNAL_CONFLICT")
        original = read_bounded(backup, LIMIT)
        if _hash(original) != entry.get("original_sha256"):
            raise IdentityError("MIGRATION_BACKUP_CHANGED")
        if _hash(data) not in {entry.get("original_sha256"), entry.get("migrated_sha256")}:
            raise IdentityError("MIGRATION_CATALOG_CHANGED: không ghi đè thay đổi sau chuyển đổi")
    else:
        entry, original = None, data
    if rollback:
        if entry is None:
            raise IdentityError("MIGRATION_NOT_FOUND")
        _atomic_write(catalog, original)
        return {"status": "ROLLED_BACK", "original_sha256": _hash(original)}
    try:
        rows = json.loads(original)
    except (ValueError, UnicodeError):
        raise IdentityError("MIGRATION_CATALOG_INVALID") from None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise IdentityError("MIGRATION_CATALOG_INVALID")
    converted = []
    keys = set()
    for row in rows:
        key = key_from_row(row, kind)
        if key.serialize() in keys:
            raise IdentityError("MIGRATION_DUPLICATE_KEY: cần kiểm tra các hàng trùng")
        keys.add(key.serialize())
        converted.append({**row, "account_key": key.account_key, "nguon": key.source,
                          "record_key": key.serialize(), "identity_version": IDENTITY_VERSION})
    payload = json.dumps(converted, ensure_ascii=False, indent=2).encode("utf-8")
    expected = {"schema_version": VERSION, "catalog": catalog.name, "kind": kind,
                "original_sha256": _hash(original), "migrated_sha256": _hash(payload)}
    if entry is not None and entry != expected:
        raise IdentityError("MIGRATION_PLAN_CHANGED")
    if apply:
        if entry is None:
            # Never replace an unrelated preexisting backup/journal.
            with backup.open("xb") as stream:
                stream.write(original)
            with journal.open("x", encoding="utf-8") as stream:
                json.dump(expected, stream, sort_keys=True)
        _atomic_write(catalog, payload)
    return {"status": "APPLIED" if apply else "PREVIEW", "rows": len(rows),
            "unknown_accounts": sum(row["account_key"] == "UNKNOWN" for row in converted),
            **expected}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chuyển metadata cũ; không gán chủ sở hữu thư mục/tệp")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--kind", required=True, choices=("DECLARATION", "GNT", "NOTICE"))
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--apply", action="store_true")
    actions.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = migrate(args.catalog, args.kind, apply=args.apply, rollback=args.rollback)
    except (IdentityError, OSError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "code": str(error)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
