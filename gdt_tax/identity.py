"""Versioned account/source/kind identity; never a credential or anonymization."""
from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ConfigError

UNKNOWN = "UNKNOWN"
IDENTITY_VERSION = "record-key-v1"
_FIELDS = {"DECLARATION": ("ma_ho_so", UNKNOWN), "GNT": ("ctu_id", "GNT"),
           "NOTICE": ("message_id", "TB")}


class IdentityError(ConfigError):
    """Invalid, conflicting or insufficiently scoped record identity."""


def account_fingerprint(username: str) -> str:
    if not isinstance(username, str) or not username.strip():
        raise IdentityError("ACCOUNT_IDENTITY_REQUIRED")
    # Preserve case and identifier spelling; do not merge accounts by guessing.
    return hashlib.sha256(username.encode("utf-8")).hexdigest()


def _validate(value: str, *, empty=False) -> None:
    if (not isinstance(value, str) or not empty and not value
            or len(value) > 2048 or any(ord(char) < 32 for char in value)):
        raise IdentityError("RECORD_KEY_FIELD_INVALID")


def _encode(prefix: str, values: list[str]) -> str:
    data = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return prefix + base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(token: str, prefix: str, count: int) -> list[str]:
    if not isinstance(token, str) or not token.startswith(prefix) or len(token) > 128 * 1024:
        raise IdentityError("RECORD_KEY_VERSION_OR_ENCODING_UNSUPPORTED")
    encoded = token[len(prefix):]
    try:
        data = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        values = json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise IdentityError("RECORD_KEY_INVALID") from None
    if (not isinstance(values, list) or len(values) != count
            or any(not isinstance(value, str) for value in values)
            or _encode(prefix, values) != token):
        raise IdentityError("RECORD_KEY_NOT_CANONICAL")
    return values


@dataclass(frozen=True, order=True)
class RecordKey:
    account_key: str
    source: str
    document_kind: str
    remote_id: str

    def __post_init__(self) -> None:
        for value in (self.account_key, self.source, self.document_kind, self.remote_id):
            _validate(value)

    @property
    def owned(self) -> bool:
        return self.account_key != UNKNOWN and self.source != UNKNOWN

    def serialize(self) -> str:
        return _encode("rk1.", [self.account_key, self.source, self.document_kind, self.remote_id])

    @classmethod
    def parse(cls, token: str) -> RecordKey:
        return cls(*_decode(token, "rk1.", 4))

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.serialize().encode("ascii")).hexdigest()


@dataclass(frozen=True, order=True)
class AttachmentKey:
    parent: RecordKey
    source: str
    remote_id: str
    loai_tra_cuu: str = ""
    loai_tbao: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.parent, RecordKey):
            raise IdentityError("ATTACHMENT_PARENT_KEY_REQUIRED")
        _validate(self.source)
        _validate(self.remote_id)
        _validate(self.loai_tra_cuu, empty=True)
        _validate(self.loai_tbao, empty=True)

    def serialize(self) -> str:
        return _encode("ak1.", [self.parent.serialize(), self.source, self.remote_id,
                                self.loai_tra_cuu, self.loai_tbao])

    @classmethod
    def parse(cls, token: str) -> AttachmentKey:
        parent, source, remote_id, lookup, kind = _decode(token, "ak1.", 5)
        return cls(RecordKey.parse(parent), source, remote_id, lookup, kind)


def key_from_row(row: Mapping[str, Any], document_kind: str) -> RecordKey:
    """Read old metadata as UNKNOWN ownership, never assign the active account."""
    if document_kind not in _FIELDS:
        raise IdentityError("RECORD_KIND_UNSUPPORTED")
    id_field, default_source = _FIELDS[document_kind]
    key = RecordKey.parse(row["record_key"]) if row.get("record_key") else None
    account = row.get("account_key", key.account_key if key else UNKNOWN)
    source = row.get("nguon", key.source if key else default_source)
    remote = row.get(id_field, key.remote_id if key else "")
    observed = RecordKey(account, source, document_kind, remote)
    if key is not None and observed != key:
        raise IdentityError("RECORD_KEY_METADATA_CONFLICT")
    return observed


def scope_targets(targets: Iterable[str], *, account_key: str, sources: Iterable[str],
                  document_kind: str) -> set[str]:
    """Bare IDs are compatible only when a single source is known in advance."""
    allowed = set(sources)
    result = set()
    for token in targets:
        if not isinstance(token, str):
            raise IdentityError("TARGET_KEY_INVALID")
        if token.startswith("rk1."):
            key = RecordKey.parse(token)
        else:
            _validate(token)
            if token.startswith("rk") and token.partition(".")[0][2:].isdigit():
                raise IdentityError("RECORD_KEY_VERSION_OR_ENCODING_UNSUPPORTED")
            if len(allowed) != 1:
                raise IdentityError("LEGACY_TARGET_AMBIGUOUS: use an account/source record key")
            key = RecordKey(account_key, next(iter(allowed)), document_kind, token)
        if key.account_key != account_key or key.source not in allowed or key.document_kind != document_kind:
            raise IdentityError("TARGET_SCOPE_MISMATCH")
        result.add(key.serialize())
    return result
