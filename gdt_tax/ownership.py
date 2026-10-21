"""Directory ownership is independent of content validity and portal identity."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .identity import UNKNOWN, IdentityError, account_fingerprint

OWNER_NAME = ".gdt-owner.json"
OWNER_VERSION = "directory-owner-v1"


def check_owner(directory: str | Path, account_key: str, *, create: bool = False) -> None:
    """Reject legacy/unowned tax data; never infer its account from the caller."""
    if not account_key or account_key == UNKNOWN:
        raise IdentityError("DIRECTORY_ACCOUNT_REQUIRED")
    directory = Path(directory)
    manifest = directory / OWNER_NAME
    if directory.is_symlink() or manifest.is_symlink():
        raise IdentityError("DIRECTORY_OWNER_UNSAFE")
    if manifest.exists():
        try:
            if manifest.stat().st_size > 4096:
                raise ValueError
            owner = json.loads(manifest.read_bytes())
        except (OSError, ValueError):
            raise IdentityError("DIRECTORY_OWNER_INVALID") from None
        if not isinstance(owner, dict) or owner.get("schema_version") != OWNER_VERSION:
            raise IdentityError("DIRECTORY_OWNER_VERSION_UNSUPPORTED")
        if owner.get("account_key") != account_key:
            raise IdentityError("DIRECTORY_ACCOUNT_MISMATCH: chọn thư mục của tài khoản hiện tại")
        return
    # Logs/settings may already exist, but tax artifacts and catalogs cannot be
    # adopted. A symlink or subdirectory is also not an empty output namespace.
    if directory.exists() and any(path.is_symlink() or path.is_dir()
            or path.suffix.lower() in {".zip", ".xml", ".pdf", ".json", ".csv", ".xlsx"}
            for path in directory.iterdir()):
        raise IdentityError("DIRECTORY_LEGACY_UNOWNED: dùng thư mục mới; xem gdt-migrate-identity")
    if not create:
        return
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"schema_version": OWNER_VERSION, "account_key": account_key},
                         sort_keys=True).encode("utf-8")
    try:
        # Exclusive creation prevents concurrent accounts from both claiming it.
        with manifest.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        check_owner(directory, account_key)


def prepare_output(settings) -> None:
    check_owner(settings.download_dir, account_fingerprint(settings.username),
                create=not settings.dry_run)
