"""Serialized catalog commits, bounded checkpoints and recoverable derived reports."""
from __future__ import annotations

import functools
import hashlib
import json
import sys
import time
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

from .errors import StorageError


@contextmanager
def catalog_lock(directory: Path, *, timeout: float = 30):
    """OS lock releases on process exit; the persistent lock file is not ownership."""
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".gdt-catalog.lock"
    if lock_path.is_symlink():
        raise StorageError("CATALOG_LOCK_UNSAFE")
    with lock_path.open("a+b") as stream:
        if stream.seek(0, 2) == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, PermissionError, OSError):
                if time.monotonic() >= deadline:
                    raise StorageError("CATALOG_BUSY: tiến trình khác đang ghi catalog") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def serialized_catalog(writer):
    @functools.wraps(writer)
    def wrapped(directory, records, **kwargs):
        records = records if isinstance(records, Mapping) else tuple(records)
        if not records:
            return None
        with catalog_lock(Path(directory)):
            return writer(directory, records, **kwargs)
    return wrapped


def generation(catalog: Path, derived: list[Path], *, ready: bool) -> None:
    from .storage import _atomic_write
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    payload = {"schema_version": "catalog-generation-v1", "catalog_sha256": digest,
               "status": "READY" if ready else "PENDING",
               "derived": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in derived} if ready else {}}
    _atomic_write(catalog.with_name(".gdt-" + catalog.name + ".generation.json"),
                  json.dumps(payload, sort_keys=True).encode())


def reports_current(catalog: Path) -> bool:
    try:
        payload = json.loads(catalog.with_name(".gdt-" + catalog.name + ".generation.json").read_bytes())
        return (payload.get("schema_version") == "catalog-generation-v1" and payload.get("status") == "READY"
                and bool(payload.get("derived"))
                and payload.get("catalog_sha256") == hashlib.sha256(catalog.read_bytes()).hexdigest()
                and all(Path(name).name == name and hashlib.sha256((catalog.parent / name).read_bytes()).hexdigest() == digest
                        for name, digest in payload["derived"].items()))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


class CatalogCheckpoint:
    def __init__(self, writer, directory, *, enabled=True, clock=time.monotonic):
        self.writer, self.directory, self.enabled, self.clock = writer, directory, enabled, clock
        self.count, self.updated = 0, clock()

    def persist(self, records, *, materialize=False, force=False):
        if not self.enabled or not records:
            return None
        if not (materialize or force or len(records) - self.count >= 100 or self.clock() - self.updated >= 30):
            return None
        result = self.writer(self.directory, records, materialize=materialize)
        self.count, self.updated = len(records), self.clock()
        return result


def flush_on_error(run):
    @functools.wraps(run)
    def wrapped(self):
        try:
            return run(self)
        except BaseException:
            # Finish a bounded commit at controlled cancellation/error boundaries.
            # A failed report leaves PENDING; do not replace the original failure.
            try:
                self._persist(self.records, materialize=True)
            except Exception as error:
                self.logger.error("CATALOG_FLUSH_FAILED: %s", type(error).__name__)
            raise
    return wrapped
