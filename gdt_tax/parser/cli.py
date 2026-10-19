"""CLI offline parse tờ khai từ manifest inventory.

Đọc ``manifest_artifact.json`` (do ``gdt_tax.inventory`` sinh ra), parse từng XML
trong ZIP nguồn, ghi kết quả theo ``artifact_id`` + ``sha256`` + ``parser_version``.
Không cần tài khoản/CAPTCHA/mạng; chạy lại cùng input/version không tạo bản trùng.

    python -m gdt_tax.parser.cli download --output download
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import zipfile
from pathlib import Path

from ..atomic import replace_with_retry
from ..errors import GdtError
from ..inventory import MANIFEST_NAME
from ..logging_setup import configure_streams
from ..run_hooks import RunHooks
from .extract import PARSER_VERSION, SCHEMA_VERSION, extract_declaration
from .registry import load_registry

LOGGER_NAME = "gdt_tax.parser.cli"
PARSED_NAME = "parsed_declarations.json"


def _read_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GdtError(f"Không đọc được manifest {path}: {error}") from error
    if not isinstance(payload, dict):
        raise GdtError(f"Manifest {path} không phải object")
    return payload


def _read_member_bytes(
    root: Path, rel_path: str, member_name: str, *, is_archive: bool
) -> bytes | None:
    path = root / rel_path
    try:
        # Inventory nhận diện định dạng từ bytes, nên ZIP bị đổi đuôi vẫn phải
        # được đọc như archive. Không suy định dạng lại từ tên file ở đây.
        if is_archive:
            with zipfile.ZipFile(path) as archive:
                return archive.read(member_name)
        return path.read_bytes()
    except (OSError, zipfile.BadZipFile, KeyError, RuntimeError):
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
            if data is None:
                log.warning("Không đọc lại được %s::%s", rel_path, member_name)
                continue
            declaration = extract_declaration(
                data,
                artifact_id=artifact.get("artifact_id"),
                source_zip=rel_path,
                source_inner_file=member_name,
                source_sha256=artifact.get("sha256"),
                registry=registry,
            )
            results.append(declaration.to_dict())
    return results


def write_parsed(results: list[dict], output_dir: Path, name: str = PARSED_NAME) -> Path:
    target = output_dir / name
    payload = {
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "count": len(results),
        "declarations": results,
    }
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
        target = write_parsed(results, output)
    except GdtError as error:
        log.error("%s", error)
        return 1
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
    return 0


__all__ = ["PARSED_NAME", "main", "parse_manifest", "write_parsed"]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
