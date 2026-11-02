"""Persistent, account-owned inventory. Connections belong to one operation/thread.

DELETE journaling intentionally supports more filesystems than WAL. Online
checkpoints commit independently of derived JSON/Excel exports; failed exports
cannot roll back discovered documents. No operation replaces the inventory.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from .identity import AttachmentKey, IdentityError, key_from_row
from .ownership import check_owner

KINDS = {"tax": "DECLARATION", "gnt": "GNT", "notice": "NOTICE"}
DATES = {"tax": "ngay_nop", "gnt": "ngay_lap", "notice": "ngay_gui"}
FILES = {"tax": "tep_zip", "gnt": "tep_xml", "notice": "tep_pdf"}
CATALOGS = {"tax": "danh_sach_ho_so.json", "gnt": "danh_sach_giay_nop_tien.json",
            "notice": "danh_sach_thong_bao.json"}
SCHEMA_VERSION = 1


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_date(value) -> str | None:
    if isinstance(value, date):
        return value.isoformat()[:10]
    text = str(value or "").strip().split(" ")[0].split("T")[0]
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return None


def merge_metadata(old: dict, new: dict) -> dict:
    merged = dict(old)
    for field, value in new.items():
        if value not in (None, "", [], {}):
            if field == '_notices' and isinstance(value, list):
                notices = {item.get('reference_key') or item.get('path'): item for item in old.get(field, [])}
                notices.update({item.get('reference_key') or item.get('path'): item for item in value})
                merged[field] = list(notices.values())
                continue
            if field == "_file_status" and value == "not_downloaded" and old.get(field) == "downloaded":
                continue
            if field in {"trang_thai", "_cqt_status"} and str(value).lower() in {"unknown", "không rõ"} and old.get(field):
                continue
            merged[field] = value
    return merged


class LocalCatalog:
    def __init__(self, directory: str | Path, account_key: str):
        self.root = Path(directory).resolve()
        self.account = account_key
        check_owner(directory, account_key, create=True)
        self.path = self.root / "catalog.sqlite3"
        if self.path.is_symlink():
            raise IdentityError("CATALOG_PATH_UNSAFE")
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise ValueError("Phiên bản database mới hơn ứng dụng; giữ nguyên dữ liệu")
            if version == 0:
                if self.path.stat().st_size:
                    self.backup()
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS documents(
                        account_key TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('tax','gnt','notice')),
                        record_key TEXT NOT NULL, source TEXT NOT NULL, remote_id TEXT NOT NULL,
                        document_kind TEXT NOT NULL, date_basis TEXT NOT NULL, document_date TEXT,
                        raw_metadata_json TEXT NOT NULL, first_seen_at TEXT NOT NULL,
                        last_seen_at TEXT NOT NULL, last_online_seen_at TEXT,
                        PRIMARY KEY(account_key,mode,record_key));
                    CREATE INDEX IF NOT EXISTS ix_documents_period ON documents(account_key,mode,document_date);
                    CREATE TABLE IF NOT EXISTS artifacts(
                        account_key TEXT NOT NULL, mode TEXT NOT NULL, record_key TEXT NOT NULL,
                        artifact_role TEXT NOT NULL, artifact_key TEXT NOT NULL, relative_path TEXT,
                        byte_size INTEGER, sha256 TEXT, evidence_json TEXT,
                        verification_state TEXT NOT NULL DEFAULT 'unknown', last_verified_at TEXT,
                        PRIMARY KEY(account_key,mode,record_key,artifact_role,artifact_key),
                        FOREIGN KEY(account_key,mode,record_key) REFERENCES documents(account_key,mode,record_key));
                    CREATE TABLE IF NOT EXISTS sync_runs(
                        run_id TEXT PRIMARY KEY, account_key TEXT NOT NULL, mode TEXT NOT NULL,
                        from_date TEXT, to_date TEXT, operation TEXT, state TEXT NOT NULL,
                        started_at TEXT NOT NULL, ended_at TEXT, metrics_json TEXT);
                    CREATE TABLE IF NOT EXISTS migration_sources(
                        source_fingerprint TEXT PRIMARY KEY, source_name TEXT NOT NULL,
                        imported_at TEXT NOT NULL, report_json TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS quarantine(
                        fingerprint TEXT PRIMARY KEY, mode TEXT NOT NULL, reason TEXT NOT NULL,
                        raw_metadata_json TEXT NOT NULL, created_at TEXT NOT NULL);
                    PRAGMA user_version=1;
                    INSERT OR IGNORE INTO schema_migrations VALUES(1,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
                    COMMIT;
                """)
            if version == 0 and self.integrity_check() != "ok":
                raise ValueError("Database không toàn vẹn; giữ nguyên để phục hồi từ backup")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            db.row_factory = sqlite3.Row
            with db:
                yield db
        finally:
            db.close()

    def backup(self) -> Path:
        target = self.path.with_name("catalog.backup-" + uuid4().hex + ".sqlite3")
        with self.connection() as source:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
            finally:
                dest.close()
        return target

    def integrity_check(self) -> str:
        with self.connection() as db:
            return str(db.execute("PRAGMA integrity_check").fetchone()[0])

    def _relative(self, value) -> str | None:
        if not value:
            return None
        path = (self.root / str(value)).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise IdentityError("ARTIFACT_PATH_OUTSIDE_WORKSPACE")
        return path.relative_to(self.root).as_posix()

    def upsert_documents(self, mode: str, rows, *, online: bool = False) -> dict:
        kind = KINDS[mode]
        counts = {"new": 0, "updated": 0, "unchanged": 0, "quarantined": 0}
        stamp = now()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for original in rows:
                row = {k: v for k, v in dict(original).items() if k not in {"_search_blob"}}
                try:
                    key = key_from_row(row, kind)
                    if not key.owned or key.account_key != self.account:
                        raise IdentityError("CATALOG_ACCOUNT_OR_SOURCE_MISMATCH")
                    allowed = {'tax': {'DVC', 'ETAX', 'ETAX_LEGACY'}, 'gnt': {'GNT'}, 'notice': {'TB'}}
                    if key.source not in allowed[mode]:
                        raise IdentityError('CATALOG_SOURCE_UNSUPPORTED')
                    relative = self._relative(row.get("_file_path") or row.get(FILES[mode]))
                    row.update(record_key=key.serialize(), account_key=self.account, nguon=key.source)
                    if relative:
                        row[FILES[mode]] = relative
                        row["_file_path"] = str(self.root / relative)
                except (IdentityError, TypeError, ValueError) as error:
                    raw = json.dumps(row, ensure_ascii=False, sort_keys=True)
                    db.execute("INSERT OR IGNORE INTO quarantine VALUES(?,?,?,?,?)",
                               (hashlib.sha256((mode + raw).encode()).hexdigest(), mode, str(error), raw, stamp))
                    counts["quarantined"] += 1
                    continue
                token = key.serialize()
                old = db.execute("SELECT raw_metadata_json FROM documents WHERE account_key=? AND mode=? AND record_key=?",
                                 (self.account, mode, token)).fetchone()
                merged = merge_metadata(json.loads(old[0]) if old else {}, row)
                raw = json.dumps(merged, ensure_ascii=False, sort_keys=True)
                counts["new" if not old else "unchanged" if old[0] == raw else "updated"] += 1
                db.execute("""INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(account_key,mode,record_key) DO UPDATE SET
                        document_date=excluded.document_date, raw_metadata_json=excluded.raw_metadata_json,
                        last_seen_at=excluded.last_seen_at,
                        last_online_seen_at=COALESCE(excluded.last_online_seen_at,documents.last_online_seen_at)""",
                           (self.account, mode, token, key.source, key.remote_id, kind, DATES[mode],
                            iso_date(merged.get(DATES[mode])), raw, stamp, stamp, stamp if online else None))
                if relative:
                    self._artifact(db, mode, token, "primary", token, relative, merged, stamp)
                for item in row.get("_notices", []):
                    attachment = item.get("attachment_key") or item.get("reference_key") or item.get("key")
                    if not attachment:
                        continue
                    try:
                        parsed = AttachmentKey.parse(attachment)
                        if parsed.parent != key:
                            raise IdentityError("ATTACHMENT_PARENT_MISMATCH")
                        path = self._relative(item.get("path") or item.get("file_path"))
                        self._artifact(db, mode, token, "attachment", attachment, path, item, stamp)
                    except (IdentityError, TypeError) as error:
                        raw_attachment = json.dumps(item, ensure_ascii=False, sort_keys=True)
                        db.execute("INSERT OR IGNORE INTO quarantine VALUES(?,?,?,?,?)",
                                   (hashlib.sha256((mode + raw_attachment).encode()).hexdigest(), mode,
                                    str(error), raw_attachment, stamp))
                        counts["quarantined"] += 1
        return counts

    def _artifact(self, db, mode, key, role, artifact_key, relative, row, stamp):
        state = 'unknown'
        if row.get('reference_status') == 'INVALID' or row.get('_integrity_status') == 'invalid':
            state = 'invalid'
        elif (row.get('reference_status') == 'VERIFIED'
              or row.get('_file_status') == 'downloaded' and row.get('_file_hash')
              and row.get('_integrity_status') in {'verified', 'unverified'}):
            state = 'verified'
        db.execute("""INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(account_key,mode,record_key,artifact_role,artifact_key) DO UPDATE SET
                relative_path=COALESCE(excluded.relative_path,artifacts.relative_path),
                byte_size=COALESCE(excluded.byte_size,artifacts.byte_size),
                sha256=COALESCE(excluded.sha256,artifacts.sha256), evidence_json=excluded.evidence_json,
                verification_state=excluded.verification_state,last_verified_at=excluded.last_verified_at""",
                   (self.account, mode, key, role, artifact_key, relative, row.get("_file_size", row.get('size')),
                    row.get("_file_hash") or row.get('sha256') or None, json.dumps(row, ensure_ascii=False),
                    state, stamp))

    def get_documents(self, mode: str, from_date=None, to_date=None, *, unknown: bool = False) -> list[dict]:
        sql = "SELECT raw_metadata_json FROM documents WHERE account_key=? AND mode=?"
        params = [self.account, mode]
        if unknown:
            sql += " AND document_date IS NULL"
        else:
            for value, op in ((from_date, ">="), (to_date, "<=")):
                if value is not None:
                    normalized = iso_date(value)
                    if normalized is None:
                        raise ValueError("Ngày lọc không hợp lệ")
                    sql += f" AND document_date {op} ?"
                    params.append(normalized)
        sql += " ORDER BY document_date,record_key"
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute(sql, params)]

    def get_counts(self, mode: str) -> dict:
        with self.connection() as db:
            total, unknown = db.execute("SELECT COUNT(*),COUNT(*)-COUNT(document_date) FROM documents WHERE account_key=? AND mode=?",
                                        (self.account, mode)).fetchone()
            review = db.execute("SELECT COUNT(*) FROM quarantine WHERE mode=?", (mode,)).fetchone()[0]
        return {"total": total, "unknown": unknown, "quarantined": review}

    def quarantine_metadata(self, mode: str, metadata: dict, reason: str) -> None:
        raw = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO quarantine VALUES(?,?,?,?,?)',
                       (hashlib.sha256((mode + raw).encode()).hexdigest(), mode, reason, raw, now()))

    def start_sync_run(self, mode, from_date, to_date, operation) -> str:
        run = uuid4().hex
        with self.connection() as db:
            db.execute("INSERT INTO sync_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (run, self.account, mode, iso_date(from_date), iso_date(to_date), operation,
                        "RUNNING", now(), None, None))
        return run

    def finish_sync_run(self, run, state, metrics=None):
        with self.connection() as db:
            db.execute("UPDATE sync_runs SET state=?,ended_at=?,metrics_json=? WHERE run_id=? AND account_key=?",
                       (state, now(), json.dumps(metrics or {}), run, self.account))

    def import_json(self, mode: str, *, dry_run: bool = False, reconcile: bool = False) -> dict:
        path = self.root / CATALOGS[mode]
        if not path.exists():
            return {"state": "MISSING", "rows": 0}
        data = path.read_bytes()
        fingerprint = hashlib.sha256(path.name.encode() + data).hexdigest()
        with self.connection() as db:
            previous = db.execute("SELECT report_json FROM migration_sources WHERE source_fingerprint=? OR (?=0 AND source_name=?) LIMIT 1",
                                  (fingerprint, int(reconcile), path.name)).fetchone()
        if previous:
            return {**json.loads(previous[0]), "state": "ALREADY_IMPORTED"}
        try:
            rows = json.loads(data)
        except ValueError as error:
            raise ValueError(f'Không đọc được {path.name}: JSON không hợp lệ') from error
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError(f"{path.name} không phải danh sách hồ sơ")
        if dry_run:
            # Run exactly the real validation/merge inside a disposable copied DB.
            import tempfile
            with tempfile.TemporaryDirectory() as directory:
                preview = LocalCatalog(directory, self.account)
                with self.connection() as source, preview.connection() as dest:
                    source.backup(dest)
                # Validate paths against the source root without touching files.
                preview.root = self.root
                result = preview.upsert_documents(mode, rows)
            return {"state": "DRY_RUN", "rows": len(rows), **result}
        backup = self.backup()
        result = self.upsert_documents(mode, rows)
        report = {"state": "IMPORTED", "rows": len(rows), "backup": backup.name, **result}
        if self.integrity_check() != "ok":
            raise ValueError("Migration không toàn vẹn; phục hồi từ backup trước khi tiếp tục")
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO migration_sources VALUES(?,?,?,?)",
                       (fingerprint, path.name, now(), json.dumps(report)))
        return report


