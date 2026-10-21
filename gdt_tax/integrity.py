"""Content-kind checks shared by download, save, resume and desktop verification.

These checks establish byte/structure integrity, not signatures or legal status.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

from lxml import etree
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .archive_limits import MAX_ARCHIVE_BYTES, MAX_MEMBER_BYTES
from .xml_policy import MAX_XML_BYTES, XmlReadError, parse_xml

VALIDATOR_VERSION = "download-integrity-v3"
DECLARATION_NS = "http://kekhaithue.gdt.gov.vn/TKhaiThue"
NOTICE_NS = "http://kekhaithue.gdt.gov.vn/TBaoThue"


@dataclass(frozen=True)
class IntegrityResult:
    status: str
    code: str
    kind: str
    size: int
    sha256: str
    validator_version: str = VALIDATOR_VERSION

    @property
    def ok(self) -> bool:
        return self.status == "OK"


def _result(data: bytes, kind: str, code: str = "OK", *, unsupported=False):
    return IntegrityResult("OK" if code == "OK" else "UNSUPPORTED" if unsupported else "REJECTED",
                           code, kind, len(data), hashlib.sha256(data).hexdigest())


def validate_xml(data: bytes, kind: str) -> IntegrityResult:
    try:
        root = parse_xml(data)
    except XmlReadError as error:
        return _result(data, kind, str(error))
    name, namespace = etree.QName(root).localname, etree.QName(root).namespace
    roots = {"declaration": {"HSoThueDTu", "HSoKhaiThue", "TKhai"},
             "gnt": {"CHUNGTU"}, "notice": {"TBao", "TBaoThue", "TBaoThueDTu"}}
    namespaces = {None, DECLARATION_NS, NOTICE_NS} if kind == 'notice' else {None, DECLARATION_NS}
    if name not in roots.get(kind, set()) or namespace not in namespaces:
        return _result(data, kind, "UNSUPPORTED_XML_KIND_OR_NAMESPACE", unsupported=True)
    return _result(data, kind)


def validate_pdf(data: bytes) -> IntegrityResult:
    if len(data) > MAX_MEMBER_BYTES:
        return _result(data, "pdf", "PDF_TOO_LARGE")
    if not data.startswith(b"%PDF-") or not re.search(rb"startxref\s+\d+\s+%%EOF\s*$", data[-2048:]):
        return _result(data, "pdf", "PDF_TRUNCATED_OR_INVALID")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            return _result(data, "pdf", "PDF_ENCRYPTED_UNVERIFIED", unsupported=True)
        pages = len(reader.pages)
        if not 1 <= pages <= 10_000:
            return _result(data, "pdf", "PDF_PAGE_LIMIT_OR_EMPTY")
        # Resolve page dictionaries; never render/execute scripts or extract streams.
        for page in reader.pages:
            if page.get("/Type") != "/Page" or page.mediabox is None:
                return _result(data, "pdf", "PDF_INVALID_PAGE_TREE")
    except (PyPdfError, ValueError, TypeError, KeyError, OSError, RecursionError, OverflowError):
        return _result(data, "pdf", "PDF_STRUCTURE_INVALID")
    return _result(data, "pdf")


def validate_tax_zip(data: bytes, *, required_kind="declaration") -> IntegrityResult:
    from .storage import valid_zip
    if not valid_zip(data):
        return _result(data, "zip", "ZIP_INTEGRITY_INVALID")
    required = False
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                path = PurePosixPath(info.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or ":" in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    return _result(data, "zip", "ZIP_UNSAFE_MEMBER")
                with archive.open(info) as stream:
                    payload = stream.read(MAX_MEMBER_BYTES + 1)
                if len(payload) > MAX_MEMBER_BYTES:
                    return _result(data, "zip", "ZIP_MEMBER_TOO_LARGE")
                if payload.startswith(b"%PDF-"):
                    result = validate_pdf(payload)
                else:
                    result = validate_xml(payload, required_kind)
                    required |= result.ok
                if not result.ok:
                    return _result(data, "zip", result.code, unsupported=result.status == "UNSUPPORTED")
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError):
        return _result(data, "zip", "ZIP_READ_ERROR")
    if not required:
        return _result(data, "zip", "ZIP_DOCUMENT_KIND_MISSING", unsupported=True)
    return _result(data, "zip")


def valid_declaration_zip(data: bytes) -> bool:
    return validate_tax_zip(data).ok


def read_bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink() or path.stat().st_size > limit:
        raise OSError("FILE_UNSAFE_OR_TOO_LARGE")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise OSError("FILE_TOO_LARGE")
    return data


def write_evidence(path: Path, result: IntegrityResult, source: dict) -> None:
    from .storage import _atomic_write
    payload = {**asdict(result), "source": source}
    _atomic_write(evidence_path(path), json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def evidence_path(path: Path) -> Path:
    return path.with_name(path.name + ".integrity.json")


def safe_destination(path: Path, data: bytes, source: dict) -> Path:
    """Keep conflicting/suspect originals; publish a distinct incoming file."""
    if not path.exists():
        return path
    try:
        existing = read_bounded(path, MAX_ARCHIVE_BYTES)
        if existing == data and matches_evidence(path, existing, source):
            return path
    except OSError:
        pass
    key = hashlib.sha256(json.dumps(source, sort_keys=True).encode() + b"\x00" + data).hexdigest()
    for index in range(1000):
        suffix = "" if index == 0 else "_" + str(index)
        candidate = path.with_name(path.stem + "__" + key[:16] + suffix + path.suffix)
        if not candidate.exists():
            return candidate
        try:
            existing = read_bounded(candidate, MAX_ARCHIVE_BYTES)
            if existing == data and matches_evidence(candidate, existing, source):
                return candidate
        except OSError:
            pass
    raise OSError("DOWNLOAD_DESTINATION_CONFLICT_LIMIT")


def matches_evidence(path: Path, data: bytes, source: dict, *, require: bool = False) -> bool:
    evidence = evidence_path(path)
    require = require or source.get("account_key", "UNKNOWN") != "UNKNOWN"
    if not evidence.exists():
        # Compatibility for legacy files: still require content validation by caller.
        # Account/source ownership is migrated separately by CORE-03.
        return not require
    try:
        payload = json.loads(read_bounded(evidence, 32 * 1024))
        return (isinstance(payload, dict) and payload.get("source") == source
                and payload.get("size") == len(data)
                and payload.get("sha256") == hashlib.sha256(data).hexdigest()
                and payload.get("status") == "OK")
    except (OSError, ValueError):
        return False


def candidate_paths(preferred: Path, recorded_name: str = "") -> list[Path]:
    candidates = [preferred]
    if recorded_name and Path(recorded_name).name == recorded_name:
        candidates.insert(0, preferred.parent / recorded_name)
    if preferred.parent.is_dir():
        candidates.extend(sorted(path for path in preferred.parent.iterdir()
                                 if path.name.startswith(preferred.stem + "__")
                                 and path.suffix == preferred.suffix))
    return list(dict.fromkeys(candidates))


def source_reference(record, kind: str) -> dict:
    remote_id = getattr(record, "ma_ho_so", None) or getattr(record, "ctu_id", None) or getattr(record, "message_id", "")
    return {"source": getattr(record, "nguon", {"gnt": "GNT", "pdf": "TB"}.get(kind, "UNKNOWN")),
            "kind": kind, "remote_id": remote_id, "account_key": getattr(record, "account_key", "UNKNOWN"),
            "record_key": getattr(record, "record_key", "")}


def document_limit(kind: str) -> int:
    return MAX_ARCHIVE_BYTES if kind == "zip" else MAX_XML_BYTES if kind == "gnt" else MAX_MEMBER_BYTES
