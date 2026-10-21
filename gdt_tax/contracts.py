"""Small structural interfaces; adapters need no requests.Response impersonation."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

from .identity import RecordKey
from .table_contracts import ParseDiagnostics


@runtime_checkable
class HttpResponse(Protocol):
    @property
    def status_code(self) -> int: ...
    @property
    def content(self) -> bytes: ...
    @property
    def text(self) -> str: ...
    @property
    def url(self) -> str: ...
    @property
    def headers(self) -> Mapping[str, str]: ...
    def json(self) -> Any: ...


@runtime_checkable
class Transport(Protocol):
    def get(self, path: str, **kwargs: Any) -> HttpResponse: ...
    def post(self, path: str, **kwargs: Any) -> HttpResponse: ...
    def url(self, path: str) -> str: ...
    def close(self) -> None: ...


@runtime_checkable
class Solver(Protocol):
    def solve(self, image: bytes) -> str: ...
    def close(self) -> None: ...


class Record(Protocol):
    account_key: str
    @property
    def key(self) -> RecordKey: ...
    @property
    def record_key(self) -> str: ...
    def to_dict(self) -> dict[str, str]: ...


R = TypeVar('R', bound=Record)
R_co = TypeVar('R_co', bound=Record, covariant=True)
R_contra = TypeVar('R_contra', bound=Record, contravariant=True)


class QueryOutcome(Protocol[R_co]):
    @property
    def records(self) -> Sequence[R_co]: ...
    @property
    def total_pages(self) -> int | None: ...
    @property
    def http_status(self) -> int: ...
    @property
    def diagnostics(self) -> ParseDiagnostics | None: ...


class Store(Protocol[R_contra]):
    def find_existing(self, record: R_contra) -> Path | None: ...
    def save(self, record: R_contra, data: bytes) -> Path | None: ...


@dataclass(frozen=True)
class DownloadArtifact:
    data: bytes
    media_kind: Literal['zip', 'xml', 'pdf']
    document_kind: str
    source: RecordKey

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def checked_artifact(artifact: DownloadArtifact, record: Record) -> bytes:
    if artifact.source != record.key or artifact.document_kind != record.key.document_kind:
        from .errors import DownloadError
        raise DownloadError('DOWNLOAD_ARTIFACT_SCOPE_MISMATCH')
    return artifact.data
