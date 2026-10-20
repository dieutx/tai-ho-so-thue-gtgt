"""Kiểm kê file gốc (ZIP/member) và profile cấu trúc XML — chưa parse chỉ tiêu.

Stage 02: quét **đệ quy** một thư mục nguồn (chỉ đọc), liệt kê mọi file và mọi
member bên trong ZIP, băm SHA-256, nhận diện định dạng từ **bytes** (không tin
đuôi file), và dựng *structure signature* cho từng XML để phát hiện phiên bản
cấu trúc mới. Đầu ra là manifest có phiên bản + báo cáo discovery; **không** đọc
chỉ tiêu thuế, không tự suy đoán ý nghĩa thẻ.

Nguyên tắc (theo spec):

* file nguồn là READ ONLY — không đổi tên/di chuyển/xóa/ghi đè;
* một ZIP có thể chứa nhiều XML/PDF, không giả định ``1 ZIP = 1 XML``;
* không dùng tên file để nhận diện; chỉ dùng tên để tham chiếu;
* lỗi một file không dừng cả lượt quét;
* chống Zip Slip, bomb nén, file mã hóa, XML quá lớn/quá sâu, entity expansion.

CLI chạy offline, không cần tài khoản/CAPTCHA/mạng::

    python -m gdt_tax.inventory download --output download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import zipfile
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree

from .archive_limits import (
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_BYTES,
    MAX_MEMBERS,
    MAX_TOTAL_UNCOMPRESSED,
)
from .atomic import replace_with_retry
from .errors import GdtError
from .logging_setup import configure_streams
from .outcomes import quality_summary, write_summary
from .parser.xml_reader import in_appendix, main_scope
from .run_hooks import RunHooks
from .xml_policy import (
    MAX_XML_BYTES,
    MAX_XML_DEPTH,
    MAX_XML_NODES,
    XmlPolicy,
    XmlReadError,
    parse_xml,
)

LOGGER_NAME = "gdt_tax.inventory"

#: Phiên bản schema manifest và thuật toán profile. Đổi khi thêm/bớt trường.
INVENTORY_SCHEMA_VERSION = "artifact-inventory-v2"
PROFILE_VERSION = "xml-profile-v4"

MANIFEST_NAME = "manifest_artifact.json"
DISCOVERY_JSON = "bao_cao_discovery.json"
DISCOVERY_MD = "bao_cao_discovery.md"

#: File do công cụ sinh ra (không phải artifact nguồn) — bỏ qua khi quét.
_DERIVED_NAMES = frozenset(
    {
        MANIFEST_NAME,
        DISCOVERY_JSON,
        DISCOVERY_MD,
        "danh_sach_ho_so.json",
        "danh_sach_ho_so.csv",
        "danh_sach_to_khai.xlsx",
        "danh_sach_giay_nop_tien.json",
        "danh_sach_giay_nop_tien.csv",
        "danh_sach_giay_nop_tien.xlsx",
        "danh_sach_thong_bao.json",
        "danh_sach_thong_bao.csv",
        "danh_sach_thong_bao.xlsx",
        "phan_loai_ho_so.json",
        "parsed_declarations.json",
        "phan_loai_artifact.json",
        "Tax_Return_Summary.xlsx",
    }
)

# --- Giới hạn tài nguyên (chống bomb/Zip Slip/XML quá lớn) ---
MAX_STRUCTURE_PATHS = 20_000
MAX_SIGNATURE_PATHS = 400

#: Thẻ được xem là ứng viên tham chiếu (mã giao dịch/hồ sơ/lần nộp...).
#: Không dùng "id" trần vì khớp nhầm trong tên khác ("ha*iD*en").
_REFERENCE_NAMES = re.compile(
    r"(magiaodich|maho\s*so|mahs|mahoso|messageid|sohoso|soquyetdinh|"
    r"mst|matax|solan|lanbo\s*sung|lan_nop|transactionid|submissionid)",
    re.IGNORECASE,
)

#: Heuristic nhóm thuế cho *discovery* — chỉ là gợi ý, có ghi căn cứ, không phải
#: kết luận mapping. Stage 03 sẽ phân loại chính thức theo nội dung.
_TAX_TYPE_HINTS = (
    ("GTGT", ("giá trị gia tăng", "gtgt")),
    ("TNCN", ("thu nhập cá nhân", "tncn")),
    ("TNDN", ("thu nhập doanh nghiệp", "tndn")),
    ("FCT", ("nhà thầu", "ntnn")),
    ("MON_BAI", ("môn bài", "lpmb")),
    ("TAI_NGUYEN", ("tài nguyên",)),
)


@dataclass
class XmlProfile:
    """Profile cấu trúc một XML: nhận diện mẫu/phiên bản ở mức *discovery*."""

    status: str
    root_element: str | None = None
    namespace: str | None = None
    namespaces: list[str] = field(default_factory=list)
    possible_form_code: str | None = None
    possible_form_name: str | None = None
    possible_form_version: str | None = None
    possible_filing_type: str | None = None
    possible_supplement_number: str | None = None
    possible_tax_type: str | None = None
    possible_tax_type_basis: str | None = None
    taxpayer_tax_code: str | None = None
    taxpayer_name: str | None = None
    tax_period_raw: str | None = None
    period_type: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    filing_date: str | None = None
    reference_candidates: dict[str, str] = field(default_factory=dict)
    max_depth: int = 0
    node_count: int = 0
    structure_signature: str | None = None
    #: Băm của tập tên phần tử (bỏ path) — ổn định hơn khi thiếu bảng tùy chọn.
    structure_skeleton: str | None = None
    error: str | None = None
    document_root: str | None = None
    structural_markers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Artifact:
    """Một file vật lý: hoặc member trong ZIP, hoặc file đứng riêng."""

    artifact_id: str
    container_id: str | None
    member_name: str
    format: str
    size: int
    sha256: str | None
    status: str
    error: str | None = None
    xml: XmlProfile | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Container:
    """Một ZIP (hoặc file đứng riêng) cùng danh sách member."""

    container_id: str
    rel_path: str
    size: int
    mtime: float
    sha256: str | None
    format: str
    status: str
    error: str | None = None
    case: dict[str, str] | None = None
    members: list[Artifact] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Manifest:
    """Manifest kiểm kê, có phiên bản schema để nâng cấp được."""

    schema_version: str
    profile_version: str
    generated_at: str
    root: str
    summary: dict
    containers: list[Container]
    errors: list[dict]
    cache_policy: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def detect_format(data: bytes) -> str:
    """Nhận diện định dạng từ bytes; không tin đuôi file."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:2] == b"PK":
        return "zip"
    if b"<" in data[:64]:
        return "xml"
    return "unknown"


def _localname(element: etree._Element) -> str | None:
    if not isinstance(element.tag, str):
        return None
    return etree.QName(element).localname


def _walk_xml(
    root: etree._Element, max_depth: int, max_nodes: int
) -> tuple[dict[str, etree._Element], set[str], int, int]:
    """Duyệt một lượt: trả về (first_by_name, path_set, max_depth, node_count)."""
    first_by_name: dict[str, etree._Element] = {}
    paths: set[str] = set()
    stack: list[tuple[etree._Element, int, str]] = [(root, 1, "")]
    max_seen = 0
    nodes = 0
    while stack:
        element, depth, parent_path = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            break
        if depth > max_depth:
            raise ValueError("XML_DEPTH_EXCEEDED")
        max_seen = max(max_seen, depth)
        name = _localname(element)
        if name is None:
            continue
        if name not in first_by_name:
            first_by_name[name] = element
        path = f"{parent_path}/{name}"
        if len(paths) < MAX_STRUCTURE_PATHS:
            paths.add(path)
        for child in reversed(list(element)):
            stack.append((child, depth + 1, path))
    return first_by_name, paths, max_seen, nodes


def _text(element: etree._Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return value or None


def _pick(first_by_name: dict[str, etree._Element], names: Iterable[str]) -> etree._Element | None:
    for name in names:
        element = first_by_name.get(name)
        if element is not None and _text(element):
            return element
    return None


def _guess_tax_type(form_name: str | None) -> tuple[str | None, str | None]:
    """Gợi ý nhóm thuế kèm căn cứ; chỉ dùng cho discovery, không phải mapping."""
    if not form_name:
        return None, None
    lowered = form_name.lower()
    for group, terms in _TAX_TYPE_HINTS:
        for term in terms:
            if term in lowered:
                return group, f"tenTKhai/Ten chứa {term!r}"
    return None, None


def profile_xml(data: bytes) -> XmlProfile:
    """Dựng profile cấu trúc cho một XML; lỗi thì trả ``status='error'``."""
    if len(data) > MAX_XML_BYTES:
        return XmlProfile(status="error", error="XML_TOO_LARGE")
    try:
        root = parse_xml(data, XmlPolicy(MAX_XML_BYTES, MAX_XML_DEPTH, MAX_XML_NODES))
    except XmlReadError as error:
        return XmlProfile(status="error", error=str(error))
    try:
        first_by_name, paths, max_depth, node_count = _walk_xml(
            root, MAX_XML_DEPTH, MAX_XML_NODES
        )
    except ValueError as error:
        return XmlProfile(status="error", error=str(error))

    root_name = _localname(root)
    default_ns = etree.QName(root).namespace
    namespaces = sorted({uri for uri in root.nsmap.values() if uri})

    try:
        primary, metadata = main_scope(root)
    except XmlReadError as error:
        return XmlProfile(status="error", error=str(error))
    uri = etree.QName(primary).namespace
    full_names = set(first_by_name)
    first_by_name = {}
    for node in metadata.iter():
        if isinstance(node.tag, str) and etree.QName(node).namespace == uri and not in_appendix(node):
            first_by_name.setdefault(_localname(node) or "", node)
    document = next((node for node in (primary, *primary.iterancestors()) if _localname(node) in {"HSoThueDTu", "TBao", "TKhai"}), primary)
    structural_markers = sorted({_localname(node) or "" for node in primary.iter()
                                 if isinstance(node.tag, str) and etree.QName(node).namespace == uri
                                 and (_localname(node) in {"CTieuTKhaiChinh", "HSoKhaiThue", "TBao"}
                                      or (_localname(node) or "").startswith(("PLuc", "BangKe")))})
    form_code_el = _pick(first_by_name, ("maTKhai", "MSo", "maMauBieu"))
    form_name_el = _pick(first_by_name, ("tenTKhai", "Ten", "tenMauBieu"))
    version_el = _pick(first_by_name, ("pbanTKhaiXML", "PBan", "phienBan"))
    filing_type_el = _pick(first_by_name, ("loaiTKhai", "LoaiTKhai"))
    supplement_el = _pick(first_by_name, ("soLan", "SoLan", "lanBoSung"))
    tax_code_el = _pick(first_by_name, ("mst", "MST", "maSoThue"))
    name_el = _pick(first_by_name, ("tenNNT", "TNNT", "tenNNT_"))
    period_el = _pick(first_by_name, ("kyKKhai", "KyKKhai", "kyTinhThue"))
    period_type_el = _pick(first_by_name, ("kieuKy", "KieuKy"))
    period_from_el = _pick(first_by_name, ("kyKKhaiTuNgay", "TuNgay"))
    period_to_el = _pick(first_by_name, ("kyKKhaiDenNgay", "DenNgay"))
    filing_date_el = _pick(first_by_name, ("ngayLapTKhai", "ngayKy", "NTBao"))

    form_name = _text(form_name_el)
    tax_type, basis = _guess_tax_type(form_name)

    references: dict[str, str] = {}
    for name, element in first_by_name.items():
        if _REFERENCE_NAMES.search(name):
            value = _text(element)
            if value:
                references[name] = value[:200]
    root_id = root.get("id")
    if root_id:
        references["@id"] = root_id[:200]

    signature_paths = sorted(paths)[:MAX_SIGNATURE_PATHS]
    basis_text = "\n".join(
        [
            root_name or "",
            default_ns or "",
            _text(form_code_el) or "",
            _text(version_el) or "",
            "\n".join(signature_paths),
        ]
    )
    signature = sha256_bytes(basis_text.encode("utf-8"))
    # Skeleton = tập tên phần tử (không theo path), dùng để phát hiện thay đổi
    # cấu trúc thật thay vì chỉ khác do có/không bảng tùy chọn.
    skeleton = sha256_bytes("\n".join(sorted(full_names)).encode("utf-8"))

    return XmlProfile(
        status="ok",
        root_element=root_name,
        namespace=uri,
        namespaces=namespaces,
        possible_form_code=_text(form_code_el),
        possible_form_name=form_name,
        possible_form_version=_text(version_el),
        possible_filing_type=_text(filing_type_el),
        possible_supplement_number=_text(supplement_el),
        possible_tax_type=tax_type,
        possible_tax_type_basis=basis,
        taxpayer_tax_code=_text(tax_code_el),
        taxpayer_name=_text(name_el),
        tax_period_raw=_text(period_el),
        period_type=_text(period_type_el),
        period_from=_text(period_from_el),
        period_to=_text(period_to_el),
        filing_date=_text(filing_date_el),
        reference_candidates=references,
        max_depth=max_depth,
        node_count=node_count,
        structure_signature=signature,
        structure_skeleton=skeleton,
        document_root=_localname(document),
        structural_markers=structural_markers,
    )


def _unsafe_member(name: str) -> str | None:
    """Trả lý do nếu tên member không an toàn (Zip Slip/drive/..), ngược lại None."""
    if not name or name.endswith("/"):
        return None
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        return "ABSOLUTE_PATH"
    if re.match(r"^[A-Za-z]:", normalized):
        return "WINDOWS_DRIVE"
    parts = normalized.split("/")
    if any(part in ("..", ".") for part in parts):
        return "PATH_TRAVERSAL"
    return None


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    with archive.open(info) as stream:
        return stream.read(MAX_MEMBER_BYTES + 1)


def scan_zip(path: Path, rel_path: str, container_sha: str) -> Container:
    """Kiểm kê một ZIP; mọi member lỗi được ghi riêng, không dừng cả ZIP."""
    container_id = container_sha
    members: list[Artifact] = []
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            total = 0
            for info in infos:
                member_name = info.filename
                if info.is_dir():
                    continue
                if len(members) >= MAX_MEMBERS:
                    members.append(
                        _error_artifact(container_id, member_name, "MEMBER_LIMIT_EXCEEDED")
                    )
                    break
                unsafe = _unsafe_member(member_name)
                if unsafe:
                    members.append(_error_artifact(container_id, member_name, unsafe))
                    continue
                if info.flag_bits & 0x1:
                    members.append(_error_artifact(container_id, member_name, "ENCRYPTED"))
                    continue
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    members.append(_error_artifact(container_id, member_name, "SYMLINK"))
                    continue
                if info.file_size > MAX_MEMBER_BYTES:
                    members.append(_error_artifact(container_id, member_name, "MEMBER_TOO_LARGE"))
                    continue
                ratio = _compression_ratio(info)
                if ratio is not None and ratio > MAX_COMPRESSION_RATIO:
                    members.append(_error_artifact(container_id, member_name, "SUSPICIOUS_RATIO"))
                    continue
                total += info.file_size
                if total > MAX_TOTAL_UNCOMPRESSED:
                    members.append(
                        _error_artifact(container_id, member_name, "TOTAL_SIZE_LIMIT")
                    )
                    break
                try:
                    data = _read_member(archive, info)
                except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as error:
                    members.append(
                        _error_artifact(container_id, member_name, f"READ_ERROR: {error}")
                    )
                    continue
                members.append(_artifact_from_bytes(container_id, member_name, data))
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, NotImplementedError) as error:
        return Container(
            container_id=container_id,
            rel_path=rel_path,
            size=path.stat().st_size,
            mtime=path.stat().st_mtime,
            sha256=container_sha,
            format="zip",
            status="error",
            error=f"CORRUPT_ZIP: {error}",
            members=[],
        )
    status = "ok" if all(member.status == "ok" for member in members) else "partial"
    return Container(
        container_id=container_id,
        rel_path=rel_path,
        size=path.stat().st_size,
        mtime=path.stat().st_mtime,
        sha256=container_sha,
        format="zip",
        status=status,
        members=members,
    )


def _compression_ratio(info: zipfile.ZipInfo) -> float | None:
    if info.compress_size <= 0:
        return float("inf") if info.file_size > 0 else None
    return info.file_size / info.compress_size


def _error_artifact(container_id: str | None, member_name: str, error: str) -> Artifact:
    return Artifact(
        artifact_id=sha256_bytes(f"{container_id}\x00{member_name}".encode()),
        container_id=container_id,
        member_name=member_name,
        format="unknown",
        size=0,
        sha256=None,
        status="error",
        error=error,
    )


def _artifact_from_bytes(container_id: str | None, member_name: str, data: bytes) -> Artifact:
    fmt = detect_format(data)
    profile = profile_xml(data) if fmt == "xml" else None
    digest = sha256_bytes(data)
    artifact_id = (
        sha256_bytes(f"{container_id}\x00{member_name}".encode())
        if container_id is not None
        else digest
    )
    return Artifact(
        artifact_id=artifact_id,
        container_id=container_id,
        member_name=member_name,
        format=fmt,
        size=len(data),
        sha256=digest,
        status="ok",
        xml=profile,
    )


def _load_cases(metadata_path: Path) -> dict[str, list[dict[str, str]]]:
    """Đọc danh mục hồ sơ cũ (nếu có) để nối ZIP với hồ sơ, không sửa file."""
    if not metadata_path.exists():
        return {}
    try:
        rows = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(rows, list):
        return {}
    index: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("tep_zip")
        if isinstance(name, str) and name:
            index.setdefault(Path(name).name, []).append(row)
    return index


def _case_view(rows: list[dict[str, str]]) -> dict[str, str]:
    """Rút gọn trường hồ sơ liên quan để đưa vào manifest/report."""
    row = rows[0]
    return {
        "ma_ho_so": str(row.get("ma_ho_so", "")),
        "nguon": str(row.get("nguon", "")),
        "to_khai": str(row.get("to_khai", "")),
        "ky_tinh_thue": str(row.get("ky_tinh_thue", "")),
        "loai_to_khai": str(row.get("loai_to_khai", "")),
        "lan_bo_sung": str(row.get("lan_bo_sung", "")),
        "ngay_nop": str(row.get("ngay_nop", "")),
        "trang_thai": str(row.get("trang_thai", "")),
    }


def scan_directory(
    root: str | Path,
    *,
    metadata_path: Path | None = None,
    cache: dict[str, Container] | None = None,
    force: bool = False,
    hooks: RunHooks | None = None,
    logger: logging.Logger | None = None,
    selected_paths: list[Path] | None = None,
) -> Manifest:
    """Quét đệ quy ``root`` và dựng manifest; không sửa bất kỳ file nguồn nào."""
    log = logger or logging.getLogger(LOGGER_NAME)
    base = Path(root)
    if not base.is_dir():
        raise GdtError(f"Thư mục nguồn không tồn tại hoặc không phải thư mục: {base}")
    cases = _load_cases(metadata_path) if metadata_path is not None else {}
    valid_cache = isinstance(cache, InventoryCache) and cache.root == str(base.resolve()) and cache.policy == cache_policy()
    containers: list[Container] = []
    errors: list[dict] = []
    if selected_paths is not None and any(not path.resolve().is_relative_to(base.resolve()) for path in selected_paths):
        raise GdtError("Tệp được chọn nằm ngoài thư mục nguồn")
    candidates = base.rglob("*") if selected_paths is None else iter(dict.fromkeys(
        base / path.resolve().relative_to(base.resolve()) for path in selected_paths))
    files = sorted(
        path
        for path in candidates
        if path.is_file() and path.name not in _DERIVED_NAMES
    )
    for path in files:
        (hooks or RunHooks()).check()
        rel_path = path.relative_to(base).as_posix()
        stat = path.stat()
        cached = cache.get(rel_path) if valid_cache and cache is not None else None
        if (
            not force
            and cached is not None
            and cached.size == stat.st_size
            and abs(cached.mtime - stat.st_mtime) < 1e-6
        ):
            container = deepcopy(cached)
        else:
            container = _scan_one(path, rel_path, log)
        container.case = _case_view(cases[path.name]) if len(cases.get(path.name, [])) == 1 else None
        containers.append(container)
        if container.status == "error":
            errors.append({"rel_path": rel_path, "error": container.error})
    summary = _summarize(containers, cases, files)
    return Manifest(
        schema_version=INVENTORY_SCHEMA_VERSION,
        profile_version=PROFILE_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        root=str(base.resolve()),
        summary=summary,
        containers=containers,
        errors=errors,
        cache_policy=cache_policy(),
    )


def _scan_one(path: Path, rel_path: str, log: logging.Logger) -> Container:
    try:
        head = path.read_bytes()[:8] if path.stat().st_size < 8 else _read_head(path)
    except OSError as error:
        return Container(
            container_id="",
            rel_path=rel_path,
            size=path.stat().st_size,
            mtime=path.stat().st_mtime,
            sha256=None,
            format="unknown",
            status="error",
            error=f"READ_ERROR: {error}",
        )
    digest = sha256_file(path)
    if detect_format(head) == "zip":
        log.debug("Kiểm kê ZIP %s", rel_path)
        return scan_zip(path, rel_path, digest)
    try:
        limit = MAX_XML_BYTES if detect_format(head) == "xml" else MAX_MEMBER_BYTES
        if path.stat().st_size > limit:
            return Container(container_id=digest, rel_path=rel_path, size=path.stat().st_size,
                             mtime=path.stat().st_mtime, sha256=digest, format=detect_format(head),
                             status="error", error="SOURCE_TOO_LARGE")
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            return Container(container_id=digest, rel_path=rel_path, size=len(data),
                             mtime=path.stat().st_mtime, sha256=digest, format=detect_format(head),
                             status="error", error="SOURCE_TOO_LARGE")
    except OSError as error:
        return Container(
            container_id=digest,
            rel_path=rel_path,
            size=path.stat().st_size,
            mtime=path.stat().st_mtime,
            sha256=digest,
            format=detect_format(head),
            status="error",
            error=f"READ_ERROR: {error}",
        )
    artifact = _artifact_from_bytes(None, path.name, data)
    return Container(
        container_id=digest,
        rel_path=rel_path,
        size=path.stat().st_size,
        mtime=path.stat().st_mtime,
        sha256=digest,
        format=artifact.format,
        status="ok" if artifact.status == "ok" else "error",
        members=[artifact],
    )


def _read_head(path: Path) -> bytes:
    with path.open("rb") as stream:
        return stream.read(8)


def _summarize(
    containers: list[Container], cases: dict[str, list[dict[str, str]]], files: list[Path]
) -> dict:
    formats: dict[str, int] = {}
    xml_status: dict[str, int] = {}
    tax_types: dict[str, int] = {}
    signatures: dict[str, int] = {}
    skeletons: dict[str, int] = {}
    forms: dict[str, int] = {}
    versions: dict[str, int] = {}
    acceptance: dict[str, int] = {}
    members = 0
    xml_members = 0
    matched = 0
    for container in containers:
        for artifact in container.members:
            members += 1
            formats[artifact.format] = formats.get(artifact.format, 0) + 1
            if artifact.xml is not None:
                xml_members += 1
                xml_status[artifact.xml.status] = xml_status.get(artifact.xml.status, 0) + 1
                if artifact.xml.possible_tax_type:
                    key = artifact.xml.possible_tax_type
                    tax_types[key] = tax_types.get(key, 0) + 1
                if artifact.xml.structure_signature:
                    key = artifact.xml.structure_signature
                    signatures[key] = signatures.get(key, 0) + 1
                if artifact.xml.structure_skeleton:
                    key = artifact.xml.structure_skeleton
                    skeletons[key] = skeletons.get(key, 0) + 1
                form = artifact.xml.possible_form_code or "(khong-ro)"
                forms[form] = forms.get(form, 0) + 1
                version = artifact.xml.possible_form_version or "(khong-ro)"
                versions[version] = versions.get(version, 0) + 1
        if container.case:
            matched += 1
            status = container.case.get("trang_thai") or "(khong-ro)"
            acceptance[status] = acceptance.get(status, 0) + 1
    return {
        "files": len(files),
        "containers": len(containers),
        "members": members,
        "xml_members": xml_members,
        "formats": formats,
        "xml_status": xml_status,
        "tax_type_hints": tax_types,
        "structure_signatures": len(signatures),
        "signature_counts": signatures,
        "structure_skeletons": len(skeletons),
        "skeleton_counts": skeletons,
        "form_codes": forms,
        "form_versions": versions,
        "containers_matched": matched,
        "containers_unmatched": len(containers) - matched,
        "cases_in_metadata": len(cases),
        "acceptance_status_values": acceptance,
    }


def write_manifest(manifest: Manifest, output_dir: str | Path, name: str = MANIFEST_NAME) -> Path:
    target = Path(output_dir) / name
    _atomic_write_json(target, manifest.to_dict())
    return target


class InventoryCache(dict[str, Container]):
    def __init__(self, root: str, policy: str):
        super().__init__()
        self.root, self.policy = root, policy


def cache_policy() -> str:
    values = [PROFILE_VERSION, MAX_XML_BYTES, MAX_XML_DEPTH, MAX_XML_NODES,
              MAX_MEMBER_BYTES, MAX_MEMBERS, MAX_TOTAL_UNCOMPRESSED, MAX_COMPRESSION_RATIO,
              MAX_STRUCTURE_PATHS, MAX_SIGNATURE_PATHS]
    return sha256_bytes(json.dumps(values).encode("utf-8"))


def load_cache(path: str | Path) -> dict[str, Container]:
    """Nạp manifest cũ để tái sử dụng kết quả (incremental theo path+size+mtime)."""
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        return {}
    if payload.get("profile_version") != PROFILE_VERSION or payload.get("cache_policy") != cache_policy() or not isinstance(payload.get("root"), str):
        return {}
    if not isinstance(payload.get("containers"), list):
        return {}
    cache = InventoryCache(payload["root"], payload["cache_policy"])
    for raw in payload.get("containers", []):
        if not isinstance(raw, dict) or not isinstance(raw.get("rel_path"), str):
            continue
        try:
            cache[raw["rel_path"]] = _container_from_dict(raw)
        except (KeyError, TypeError, ValueError):
            continue
    return cache


def _container_from_dict(raw: dict) -> Container:
    members = []
    for item in raw.get("members", []):
        xml_raw = item.get("xml")
        xml = XmlProfile(**xml_raw) if isinstance(xml_raw, dict) else None
        members.append(
            Artifact(
                artifact_id=item["artifact_id"],
                container_id=item.get("container_id"),
                member_name=item["member_name"],
                format=item["format"],
                size=int(item["size"]),
                sha256=item.get("sha256"),
                status=item["status"],
                error=item.get("error"),
                xml=xml,
            )
        )
    return Container(
        container_id=raw["container_id"],
        rel_path=raw["rel_path"],
        size=int(raw["size"]),
        mtime=float(raw["mtime"]),
        sha256=raw.get("sha256"),
        format=raw["format"],
        status=raw["status"],
        error=raw.get("error"),
        case=raw.get("case"),
        members=members,
    )


def build_discovery(manifest: Manifest) -> dict:
    """Tổng hợp báo cáo discovery và các điểm cần người dùng xác nhận."""
    summary = manifest.summary
    signature_counts: dict[str, int] = summary.get("signature_counts", {})
    representatives: dict[str, dict] = {}
    for container in manifest.containers:
        for artifact in container.members:
            if artifact.xml is None or not artifact.xml.structure_signature:
                continue
            signature = artifact.xml.structure_signature
            if signature in representatives:
                continue
            representatives[signature] = {
                "source_zip": container.rel_path,
                "source_inner_file": artifact.member_name,
                "root_element": artifact.xml.root_element,
                "namespace": artifact.xml.namespace,
                "possible_form_code": artifact.xml.possible_form_code,
                "possible_form_name": artifact.xml.possible_form_name,
                "possible_form_version": artifact.xml.possible_form_version,
                "possible_tax_type": artifact.xml.possible_tax_type,
                "count": signature_counts.get(signature, 0),
            }
    ambiguities: list[dict[str, str]] = []
    # Cùng form_code + version nhưng khác *skeleton* (tập tên phần tử) ⇒ có thể
    # là biến thể cấu trúc thật. Dùng skeleton ổn định, không dùng signature
    # theo path vì signature đổi chỉ vì thiếu bảng tùy chọn.
    by_form: dict[tuple, set] = {}
    for container in manifest.containers:
        for artifact in container.members:
            if artifact.xml is None or not artifact.xml.structure_skeleton:
                continue
            key = (artifact.xml.possible_form_code, artifact.xml.possible_form_version)
            by_form.setdefault(key, set()).add(artifact.xml.structure_skeleton)
    for (code, version), skeletons in sorted(by_form.items(), key=lambda item: str(item[0])):
        if len(skeletons) > 1:
            ambiguities.append(
                {
                    "type": "MULTIPLE_STRUCTURES",
                    "detail": f"form_code={code} version={version} có {len(skeletons)} skeleton khác nhau",
                }
            )
    unmapped = [
        container.rel_path
        for container in manifest.containers
        if not container.case
    ]
    if unmapped:
        ambiguities.append(
            {
                "type": "NO_CASE_METADATA",
                "detail": f"{len(unmapped)} file không khớp metadata hồ sơ (ví dụ {unmapped[0]})",
            }
        )
    no_form = [
        f"{container.rel_path}::{artifact.member_name}"
        for container in manifest.containers
        for artifact in container.members
        if artifact.xml is not None and not artifact.xml.possible_form_code
    ]
    if no_form:
        ambiguities.append(
            {
                "type": "FORM_CODE_NOT_FOUND",
                "detail": f"{len(no_form)} XML không tìm thấy mã mẫu (ví dụ {no_form[0]})",
            }
        )
    acceptance_values = summary.get("acceptance_status_values", {})
    # Portal metadata is an unverified hint, not linked legal acceptance evidence.
    has_acceptance = False
    report = {
        "schema_version": manifest.schema_version,
        "profile_version": manifest.profile_version,
        "generated_at": manifest.generated_at,
        "root": manifest.root,
        "summary": summary,
        "structure_signatures": representatives,
        "ambiguities": ambiguities,
        "acceptance_evidence_available": has_acceptance,
        "metadata_status_available": bool(acceptance_values),
        "acceptance_policy": "UNKNOWN until independently verified evidence is linked to artifact",
        "open_questions": _open_questions(),
    }
    return report


def _open_questions() -> list[dict[str, str]]:
    """Câu hỏi bắt buộc xác nhận trước khi build mapping (spec §58)."""
    return [
        {"id": "A", "question": "Thư mục có file/thông báo chứng minh CQT đã ACCEPT tờ khai không? (metadata trang_thai hiện có giá trị chấp nhận/không chấp nhận)"},
        {"id": "B", "question": "Nếu không có nguồn acceptance, toàn bộ acceptance_status mặc định UNKNOWN hay dùng metadata trang_thai?"},
        {"id": "C", "question": "Tờ khai bổ sung: giữ toàn bộ hay cần thêm chế độ chọn 'tờ khai hiệu lực cuối cùng'?"},
        {"id": "D", "question": "Các loại tờ khai khác chỉ cần inventory hay cần tổng hợp ở giai đoạn sau?"},
        {"id": "E", "question": "Phụ lục tổng hợp nào được phép lấy dữ liệu?"},
        {"id": "F", "question": "Một workbook nhiều sheet hay tách GTGT.xlsx/TNCN.xlsx/TNDN.xlsx?"},
        {"id": "G", "question": "Cần link/mở nhanh file ZIP/XML nguồn từ Excel hay chỉ cần source path?"},
        {"id": "H", "question": "Có cần database trung gian (SQLite) cho incremental processing hay chỉ Excel?"},
    ]


def write_discovery(report: dict, output_dir: str | Path) -> tuple[Path, Path]:
    directory = Path(output_dir)
    json_path = directory / DISCOVERY_JSON
    md_path = directory / DISCOVERY_MD
    _atomic_write_json(json_path, report)
    _atomic_write_text(md_path, render_discovery_markdown(report))
    return json_path, md_path


def render_discovery_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# Báo cáo Discovery — kiểm kê hồ sơ thuế",
        "",
        f"- Thư mục nguồn: `{report['root']}`",
        f"- Tạo lúc: {report['generated_at']}",
        f"- Schema: `{report['schema_version']}` / profile `{report['profile_version']}`",
        "",
        "## Tổng quan",
        "",
        f"- Số file quét: **{summary['files']}**",
        f"- Số container (ZIP/file): **{summary['containers']}**",
        f"- Số member: **{summary['members']}** (XML: {summary['xml_members']})",
        f"- Số structure signature khác nhau: **{summary['structure_signatures']}**",
        "",
        "## Định dạng member",
        "",
    ]
    for fmt, count in sorted(summary["formats"].items()):
        lines.append(f"- `{fmt}`: {count}")
    lines += [
        "",
        f"- Số skeleton cấu trúc (ổn định): **{summary['structure_skeletons']}**",
        f"- Container khớp metadata hồ sơ: **{summary['containers_matched']}** "
        f"(không khớp: {summary['containers_unmatched']})",
        "",
        "## Trạng thái parse XML",
        "",
    ]
    for status, count in sorted(summary["xml_status"].items()):
        lines.append(f"- `{status}`: {count}")
    lines += ["", "## Gợi ý nhóm thuế (heuristic, chưa phải mapping)", ""]
    for group, count in sorted(summary["tax_type_hints"].items()):
        lines.append(f"- `{group}`: {count}")
    lines += ["", "## Mã mẫu phát hiện", ""]
    for code, count in sorted(summary["form_codes"].items(), key=lambda item: str(item[0])):
        lines.append(f"- `{code}`: {count}")
    lines += ["", "## Phiên bản mẫu phát hiện", ""]
    for version, count in sorted(summary["form_versions"].items(), key=lambda item: str(item[0])):
        lines.append(f"- `{version}`: {count}")
    lines += ["", "## Trạng thái tiếp nhận (từ metadata)", ""]
    for status, count in sorted(summary["acceptance_status_values"].items()):
        lines.append(f"- {status}: {count}")
    lines += ["", "## Cấu trúc XML đại diện", ""]
    for signature, info in sorted(report["structure_signatures"].items()):
        lines.append(
            f"- `{signature[:12]}…` ×{info['count']} — root=`{info['root_element']}`, "
            f"ns=`{info['namespace']}`, form=`{info['possible_form_code']}`, "
            f"version=`{info['possible_form_version']}`, gợi ý=`{info['possible_tax_type']}`"
        )
        lines.append(f"  - mẫu: `{info['source_zip']}` → `{info['source_inner_file']}`")
    lines += ["", "## Điểm cần xác nhận", ""]
    if report["ambiguities"]:
        for item in report["ambiguities"]:
            lines.append(f"- **{item['type']}**: {item['detail']}")
    else:
        lines.append("- Không phát hiện mâu thuẫn cấu trúc.")
    lines += ["", "## Câu hỏi mở (spec §58)", ""]
    for item in report["open_questions"]:
        lines.append(f"- **{item['id']}.** {item['question']}")
    lines += [
        "",
        "> Manifest và báo cáo này chỉ chứa metadata/đường dẫn nguồn, **không** chứa "
        "chỉ tiêu thuế và **không** sửa file nguồn.",
        "",
    ]
    return "\n".join(lines)


def _atomic_write_json(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(path, data)


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(temporary, path)
    except OSError as error:
        raise GdtError(f"Không ghi được {path}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gdt-inventory",
        description=(
            "Kiểm kê file ZIP/member và profile cấu trúc XML (offline, chỉ đọc). "
            "Không parse chỉ tiêu thuế."
        ),
    )
    parser.add_argument("folder", help="Thư mục nguồn cần quét đệ quy")
    parser.add_argument("--output", help="Thư mục ghi manifest/báo cáo (mặc định: thư mục nguồn)")
    parser.add_argument("--metadata", help="File danh_sach_ho_so.json để nối ZIP với hồ sơ")
    parser.add_argument("--manifest-name", default=MANIFEST_NAME, help="Tên file manifest")
    parser.add_argument("--rehash", action="store_true", help="Bỏ qua cache, băm lại toàn bộ")
    parser.add_argument("--json-only", action="store_true", help="Chỉ ghi JSON, không ghi Markdown")
    parser.add_argument("--summary-json", help="Ghi quality summary JSON, exit 0=đủ, 1=partial, 2=input lỗi")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log chi tiết")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger(LOGGER_NAME)
    root = Path(args.folder)
    output = Path(args.output) if args.output else root
    manifest_path = output / args.manifest_name
    metadata = Path(args.metadata) if args.metadata else root / "danh_sach_ho_so.json"
    try:
        cache = {} if args.rehash else load_cache(manifest_path)
        manifest = scan_directory(root, metadata_path=metadata, cache=cache, force=args.rehash, logger=log)
        write_manifest(manifest, output, args.manifest_name)
        report = build_discovery(manifest)
        json_path, md_path = write_discovery(report, output)
    except GdtError as error:
        log.error("%s", error)
        return 2
    summary = manifest.summary
    log.info(
        "Đã kiểm kê %s file, %s container, %s member, %s signature",
        summary["files"],
        summary["containers"],
        summary["members"],
        summary["structure_signatures"],
    )
    log.info("Manifest: %s", manifest_path)
    log.info("Báo cáo: %s", json_path if args.json_only else md_path)
    quality_rows = [{"status": c.status} for c in manifest.containers]
    quality_rows.extend({"status": "error"} for c in manifest.containers for a in c.members
                        if a.status == "error" or (a.xml is not None and a.xml.status == "error"))
    outcome = quality_summary("inventory", quality_rows, complete_status="ok")
    outcome["containers"] = len(manifest.containers)
    outcome["scan_errors"] = len(manifest.errors)
    if manifest.errors:
        outcome["exit_code"] = 1
    try:
        return write_summary(args.summary_json, outcome)
    except GdtError as error:
        log.error("%s", error)
        return 2


__all__ = [
    "Artifact",
    "Container",
    "INVENTORY_SCHEMA_VERSION",
    "Manifest",
    "PROFILE_VERSION",
    "XmlProfile",
    "build_discovery",
    "detect_format",
    "load_cache",
    "main",
    "profile_xml",
    "render_discovery_markdown",
    "scan_directory",
    "scan_zip",
    "sha256_bytes",
    "sha256_file",
    "write_discovery",
    "write_manifest",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
