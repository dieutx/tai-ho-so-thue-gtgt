"""CLI offline parse tờ khai từ manifest inventory.

Đọc ``manifest_artifact.json`` (do ``gdt_tax.inventory`` sinh ra), parse từng XML
trong ZIP nguồn, ghi kết quả theo ``artifact_id`` + ``sha256`` + ``parser_version``.
Không cần tài khoản/CAPTCHA/mạng; chạy lại cùng input/version không tạo bản trùng.

    python -m gdt_tax.parser.cli download --output download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

from ..archive_limits import MAX_ARCHIVE_BYTES, MAX_COMPRESSION_RATIO, MAX_MEMBERS
from ..artifact_contracts import lineage, validate_payload
from ..atomic import replace_with_retry
from ..errors import GdtError
from ..inventory import MANIFEST_NAME, _unsafe_member
from ..logging_setup import configure_streams
from ..outcomes import quality_summary, write_summary
from ..run_hooks import RunHooks
from .extract import PARSER_VERSION, SCHEMA_VERSION, extract_declaration
from .registry import load_registry
from .xml_reader import MAX_XML_BYTES

LOGGER_NAME = "gdt_tax.parser.cli"
PARSED_NAME = "parsed_declarations.json"


def _read_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GdtError(f"Không đọc được manifest {path}: {error}") from error
    if not isinstance(payload, dict):
        raise GdtError(f"Manifest {path} không phải object")
    validate_payload(payload, "containers")
    return payload


def _read_member_bytes(
    root: Path, rel_path: str, member_name: str, *, is_archive: bool
) -> bytes | None:
    try:
        path = (root / rel_path).resolve()
        if Path(rel_path).is_absolute() or not path.is_relative_to(root.resolve()):
            return None
        # Inventory nhận diện định dạng từ bytes, nên ZIP bị đổi đuôi vẫn phải
        # được đọc như archive. Không suy định dạng lại từ tên file ở đây.
        if is_archive:
            if path.stat().st_size > MAX_ARCHIVE_BYTES or _unsafe_member(member_name):
                return None
            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo(member_name)
                if (len(archive.infolist()) > MAX_MEMBERS or info.flag_bits & 1
                        or info.file_size > MAX_XML_BYTES
                        or info.file_size / max(1, info.compress_size) > MAX_COMPRESSION_RATIO):
                    return None
                with archive.open(info) as stream:
                    data = stream.read(MAX_XML_BYTES + 1)
        else:
            if path.stat().st_size > MAX_XML_BYTES:
                return None
            with path.open('rb') as stream:
                data = stream.read(MAX_XML_BYTES + 1)
        return data if len(data) <= MAX_XML_BYTES else None
    except (OSError, ValueError, zipfile.BadZipFile, KeyError, RuntimeError, NotImplementedError, EOFError, zlib.error):
        return None


def parse_manifest(
    manifest: dict,
    root: Path,
    *,
    registry=None,
    hooks: RunHooks | None = None,
    logger: logging.Logger | None = None,
) -> list[dict]:
    """Parse mọi XML trong manifest; lỗi một artifact không dừng cả batch."""
    validate_payload(manifest, "containers")
    log = logger or logging.getLogger(LOGGER_NAME)
    results: list[dict] = []
    for container in manifest.get("containers", []):
        rel_path = container.get("rel_path")
        if not isinstance(rel_path, str):
            continue
        for artifact in container.get("members", []):
            (hooks or RunHooks()).check()
            if artifact.get("format") != "xml" or artifact.get("status") != "ok":
                continue
            member_name = artifact.get("member_name", "")
            data = _read_member_bytes(
                root,
                rel_path,
                member_name,
                is_archive=container.get("format") == "zip",
            )
            actual_hash = hashlib.sha256(data).hexdigest() if data is not None else None
            expected_hash = artifact.get('sha256')
            read_error = ('SOURCE_UNREADABLE_OR_UNSAFE: chạy Kiểm kê lại' if data is None else
                          'SOURCE_CHANGED: tệp đã đổi sau kiểm kê; chạy Kiểm kê lại'
                          if expected_hash and actual_hash != expected_hash else '')
            declaration = extract_declaration(
                b'' if read_error else (data or b''),
                artifact_id=artifact.get("artifact_id"),
                source_zip=rel_path,
                source_inner_file=member_name,
                source_sha256=expected_hash if read_error else actual_hash,
                registry=registry,
            )
            if read_error:
                declaration.error = read_error
                log.warning('%s: %s::%s', read_error, rel_path, member_name)
            results.append(declaration.to_dict())
    return results


def write_parsed(results: list[dict], output_dir: Path, name: str = PARSED_NAME, *, manifest: dict | None = None) -> Path:
    target = output_dir / name
    payload = {
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "count": len(results),
        "declarations": results,
    }
    if manifest is not None:
        payload["lineage"] = lineage(manifest)
    hashes = {row.get("registry_sha256") for row in results if row.get("registry_sha256")}
    if len(hashes) > 1:
        raise GdtError("ARTIFACT_REGISTRY_MISMATCH: mixed parser registries")
    payload["registry_sha256"] = next(iter(hashes), None)
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        replace_with_retry(temporary, target)
    except OSError as error:
        raise GdtError(f"Không ghi được {target}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gdt-parse",
        description=(
            "Parse tờ khai từ manifest inventory (offline). Chưa có mapping thì "
            "trả NEED_MAPPING, không tự suy đoán chỉ tiêu."
        ),
    )
    parser.add_argument("folder", help="Thư mục nguồn chứa ZIP và manifest")
    parser.add_argument("--output", help="Thư mục ghi kết quả (mặc định: thư mục nguồn)")
    parser.add_argument("--manifest", help="Đường dẫn manifest (mặc định: <folder>/manifest)")
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
        results = parse_manifest(manifest, root, registry=registry, logger=log)
        target = write_parsed(results, output, manifest=manifest)
    except GdtError as error:
        log.error("%s", error)
        return 2
    mapped = sum(1 for item in results if item["status"] == "MAPPED")
    need = sum(1 for item in results if item["status"] == "NEED_MAPPING")
    errors = sum(1 for item in results if item["status"] == "error")
    log.info(
        "Đã parse %s tờ khai (MAPPED=%s, NEED_MAPPING=%s, error=%s)",
        len(results),
        mapped,
        need,
        errors,
    )
    log.info("Kết quả: %s", target)
    summary = quality_summary("parse", results, complete_status="MAPPED")
    try:
        return write_summary(args.summary_json, summary)
    except GdtError as error:
        log.error("%s", error)
        return 2


__all__ = ["PARSED_NAME", "main", "parse_manifest", "write_parsed"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
