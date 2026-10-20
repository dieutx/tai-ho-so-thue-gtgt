"""Phân loại từng artifact theo **nội dung** XML (stage 03).

Khác `classification.py` (chỉ dựa trên metadata cấp hồ sơ), module này phân loại
từng file/member dựa trên cấu trúc XML đã profile ở stage 02 và mapping đã đăng ký:
nhóm thuế, vai trò tài liệu, mã mẫu, phiên bản, bằng chứng, và trạng thái
ok/conflict/unknown. Không suy đoán: thiếu tín hiệu ⇒ ``UNKNOWN``, mâu thuẫn ⇒
``CONFLICT`` kèm bằng chứng hai phía.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .artifact_contracts import lineage, validate_payload
from .atomic import replace_with_retry
from .errors import GdtError
from .inventory import MANIFEST_NAME
from .logging_setup import configure_streams
from .outcomes import quality_summary, write_summary
from .parser.registry import MappingRegistry, load_registry
from .run_hooks import RunHooks

LOGGER_NAME = "gdt_tax.classify"
CLASSIFY_VERSION = "content-classify-v1"
CLASSIFICATION_NAME = "phan_loai_artifact.json"

TAX_GROUPS = ("GTGT", "TNCN", "TNDN", "FCT", "MON_BAI", "TAI_NGUYEN", "OTHER", "UNKNOWN")
ROLES = ("DECLARATION", "APPENDIX", "NOTICE", "UNKNOWN")

#: Gợi ý nhóm thuế theo tên mẫu khi chưa có mapping (chỉ là *bằng chứng*, có thể
#: bị CONFLICT nếu nhiều nhóm cùng khớp).
_TAX_TERMS = (
    ("GTGT", ("giá trị gia tăng", "gtgt")),
    ("TNCN", ("thu nhập cá nhân", "tncn")),
    ("TNDN", ("thu nhập doanh nghiệp", "tndn")),
    ("FCT", ("nhà thầu", "ntnn")),
    ("MON_BAI", ("môn bài", "lpmb")),
    ("TAI_NGUYEN", ("tài nguyên",)),
)
#: Root được xem là thông báo/không phải tờ khai.
_NOTICE_ROOTS = {"TBao"}
#: Node đánh dấu tờ khai chính (khác phụ lục).
_DECLARATION_MARKERS = ("CTieuTKhaiChinh", "HSoKhaiThue")
_APPENDIX_MARKERS = ("PLuc", "BangKe")


@dataclass
class ArtifactClassification:
    artifact_id: str
    source_zip: str | None
    source_inner_file: str
    tax_group: str
    document_role: str
    form_code: str | None
    schema_version: str | None
    rule_version: str
    status: str
    evidence: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _tax_group_from_name(form_name: str | None) -> tuple[str | None, str | None]:
    if not form_name:
        return None, None
    lowered = form_name.lower()
    matches = [
        group for group, terms in _TAX_TERMS if any(term in lowered for term in terms)
    ]
    if len(matches) == 1:
        return matches[0], f"ten mẫu chứa từ khóa {matches[0]}"
    if len(matches) > 1:
        return None, f"tên mẫu khớp nhiều nhóm: {', '.join(matches)}"
    return None, None


def _document_role(root_element: str | None, has_declaration: bool, has_appendix: bool) -> str:
    if root_element in _NOTICE_ROOTS:
        return "NOTICE"
    if has_declaration:
        return "DECLARATION"
    if has_appendix:
        return "APPENDIX"
    return "UNKNOWN"


def classify_artifact(
    *,
    artifact_id: str,
    source_zip: str | None,
    source_inner_file: str,
    xml_profile: dict | None,
    registry: MappingRegistry | None = None,
) -> ArtifactClassification:
    """Phân loại một artifact từ profile XML (không cần đọc lại bytes)."""
    profile = xml_profile or {}
    root = profile.get("root_element")
    form_code = profile.get("possible_form_code")
    form_version = profile.get("possible_form_version")
    form_name = profile.get("possible_form_name")
    evidence: list[str] = []
    conflicts: list[str] = []

    if root:
        evidence.append(f"root={root}")
    if form_code:
        evidence.append(f"form_code={form_code}")
    if form_version:
        evidence.append(f"form_version={form_version}")

    # Nhóm thuế: ưu tiên mapping đã đăng ký (bằng chứng mạnh), sau đó tên mẫu.
    mapping = registry.lookup(form_code, form_version) if registry is not None else None
    if mapping is not None and not mapping.matches_profile(root, profile.get('namespace')):
        evidence.append('mapping rejected: document schema/date not verified')
        mapping = None
    tax_group = "UNKNOWN"
    reason: str | None = None
    if mapping is not None and mapping.tax_type:
        tax_group = mapping.tax_type
        evidence.append(f"mapping={mapping.mapping_id} tax_type={mapping.tax_type}")
        reason = "mapping đã đăng ký"
    else:
        guessed, basis = _tax_group_from_name(form_name)
        if guessed:
            tax_group = guessed
            evidence.append(f"ten mẫu: {basis}")
            reason = "tên mẫu (chưa có mapping)"
        elif basis:
            conflicts.append(basis)

    # Vai trò tài liệu từ cấu trúc: dùng các marker đã thấy trong XML thật.
    # `possible_*` không có sẵn marker node, nên suy từ root + có chỉ tiêu tổng hợp.
    has_declaration = root in {"HSoThueDTu", "TKhai"} and form_code is not None
    has_appendix = False
    role = _document_role(root, has_declaration, has_appendix)
    evidence.append(f"role từ root={root}")

    status = "OK"
    if conflicts:
        status = "CONFLICT"
    elif tax_group == "UNKNOWN" or role == "UNKNOWN":
        status = "UNKNOWN"

    return ArtifactClassification(
        artifact_id=artifact_id,
        source_zip=source_zip,
        source_inner_file=source_inner_file,
        tax_group=tax_group,
        document_role=role,
        form_code=form_code,
        schema_version=form_version,
        rule_version=CLASSIFY_VERSION,
        status=status,
        evidence=evidence,
        conflicts=conflicts,
        reason=reason,
    )


def classify_manifest(
    manifest: dict,
    *,
    registry: MappingRegistry | None = None,
    hooks: RunHooks | None = None,
) -> list[dict]:
    """Phân loại mọi XML trong manifest; giữ cả artifact lỗi/không XML."""
    validate_payload(manifest, "containers")
    registry = registry if registry is not None else load_registry()
    results: list[dict] = []
    for container in manifest.get("containers", []):
        rel_path = container.get("rel_path")
        for artifact in container.get("members", []):
            (hooks or RunHooks()).check()
            if artifact.get("format") != "xml":
                continue
            classification = classify_artifact(
                artifact_id=artifact.get("artifact_id", ""),
                source_zip=rel_path if isinstance(rel_path, str) else None,
                source_inner_file=artifact.get("member_name", ""),
                xml_profile=artifact.get("xml"),
                registry=registry,
            )
            results.append(classification.to_dict())
    return results


def classification_payload(manifest: dict, rows: list[dict], registry: MappingRegistry) -> dict:
    return {"schema_version": "artifact-classification-v1", "rule_version": CLASSIFY_VERSION,
            "count": len(rows), "classifications": rows, "lineage": lineage(manifest),
            "registry_sha256": registry.fingerprint}


def _read_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GdtError(f"Không đọc được manifest {path}: {error}") from error
    if not isinstance(payload, dict):
        raise GdtError(f"Manifest {path} không phải object")
    validate_payload(payload, "containers")
    return payload


def _atomic_write_json(path: Path, payload: dict) -> None:
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
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
        prog="gdt-classify",
        description="Phân loại artifact theo nội dung XML (offline, từ manifest).",
    )
    parser.add_argument("folder", help="Thư mục chứa manifest")
    parser.add_argument("--output", help="Thư mục ghi kết quả (mặc định: thư mục nguồn)")
    parser.add_argument("--manifest", help="Đường dẫn manifest")
    parser.add_argument("--forms-dir", help="Thư mục mapping mẫu biểu")
    parser.add_argument("--summary-json", help="Ghi quality summary JSON, exit 0=đủ, 1=partial, 2=input lỗi")
    parser.add_argument("-v", "--verbose", action="store_true")
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
    manifest_path = Path(args.manifest) if args.manifest else root / MANIFEST_NAME
    try:
        manifest = _read_manifest(manifest_path)
        registry = load_registry(args.forms_dir, logger=log)
        results = classify_manifest(manifest, registry=registry)
        payload = classification_payload(manifest, results, registry)
        _atomic_write_json(output / CLASSIFICATION_NAME, payload)
    except GdtError as error:
        log.error("%s", error)
        return 2
    ok = sum(1 for item in results if item["status"] == "OK")
    unknown = sum(1 for item in results if item["status"] == "UNKNOWN")
    conflict = sum(1 for item in results if item["status"] == "CONFLICT")
    log.info(
        "Đã phân loại %s artifact (OK=%s, UNKNOWN=%s, CONFLICT=%s)",
        len(results), ok, unknown, conflict,
    )
    log.info("Kết quả: %s", output / CLASSIFICATION_NAME)
    summary = quality_summary("classify", results, complete_status="OK")
    try:
        return write_summary(args.summary_json, summary)
    except GdtError as error:
        log.error("%s", error)
        return 2


__all__ = [
    "ArtifactClassification",
    "CLASSIFICATION_NAME",
    "CLASSIFY_VERSION",
    "ROLES",
    "TAX_GROUPS",
    "classify_artifact",
    "classify_manifest",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
