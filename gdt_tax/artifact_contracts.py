"""Validate offline stage boundaries and bind derived data to its inventory."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from .errors import GdtError

SCHEMAS = {
    "containers": "artifact-inventory-v2",
    "declarations": "parsed-declaration-v1",
    "classifications": "artifact-classification-v1",
}


def validate_payload(payload: dict, collection: str) -> list[dict]:
    if not isinstance(payload, dict):
        raise GdtError("ARTIFACT_SCHEMA_INVALID: expected object")
    version = payload.get("schema_version")
    if version is not None and version != SCHEMAS[collection]:
        raise GdtError(f"ARTIFACT_SCHEMA_UNSUPPORTED: {version}")
    rows = payload.get(collection)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise GdtError(f"ARTIFACT_SCHEMA_INVALID: {collection}")
    if "count" in payload and payload["count"] != len(rows):
        raise GdtError("ARTIFACT_COUNT_MISMATCH")
    for row in rows:
        if collection != "containers":
            for key in ("artifact_id", "source_zip", "source_inner_file", "source_sha256"):
                if row.get(key) is not None and not isinstance(row[key], str):
                    raise GdtError(f"ARTIFACT_SCHEMA_INVALID: {key}")
    if collection == "containers":
        for row in rows:
            if not isinstance(row.get("rel_path"), str) or not isinstance(row.get("members"), list):
                raise GdtError("ARTIFACT_SCHEMA_INVALID: container")
            if any(not isinstance(member, dict) for member in row["members"]):
                raise GdtError("ARTIFACT_SCHEMA_INVALID: members")
            for member in row["members"]:
                if any(member.get(key) is not None and not isinstance(member[key], str) for key in ("artifact_id", "member_name", "sha256")):
                    raise GdtError("ARTIFACT_SCHEMA_INVALID: member identity")
    elif collection == "declarations":
        for row in rows:
            if any(row.get(key) is not None and not isinstance(row[key], dict) for key in ("taxpayer", "period")):
                raise GdtError("ARTIFACT_SCHEMA_INVALID: declaration metadata")
            indicators = row.get("indicators", [])
            if not isinstance(indicators, list) or any(not isinstance(item, dict) for item in indicators):
                raise GdtError("ARTIFACT_SCHEMA_INVALID: indicators")
            for item in [row, *indicators]:
                warnings = item.get("warnings", [])
                if not isinstance(warnings, list) or any(not isinstance(warning, str) for warning in warnings):
                    raise GdtError("ARTIFACT_SCHEMA_INVALID: warnings")
    return rows


def manifest_fingerprint(manifest: dict) -> str:
    validate_payload(manifest, "containers")
    content = {key: value for key, value in manifest.items() if key != "generated_at"}
    raw = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def lineage(manifest: dict) -> dict:
    return {"contract_version": "offline-lineage-v1", "manifest_sha256": manifest_fingerprint(manifest)}


def source_key(row: dict) -> tuple[str, str, str]:
    return (row.get("artifact_id") or "", row.get("source_zip") or "", row.get("source_inner_file") or "")


def validate_bundle(manifest, parsed, classification, *, allow_legacy: bool = True) -> None:
    for payload, collection in ((manifest, "containers"), (parsed, "declarations"), (classification, "classifications")):
        if payload is None:
            if not allow_legacy:
                raise GdtError(f"ARTIFACT_INPUT_MISSING: {collection}")
            continue
        validate_payload(payload, collection)
    if manifest is None:
        return
    fingerprint = manifest_fingerprint(manifest)
    parser_registry = (parsed or {}).get("registry_sha256")
    classifier_registry = (classification or {}).get("registry_sha256")
    if parser_registry and classifier_registry and parser_registry != classifier_registry:
        raise GdtError("ARTIFACT_REGISTRY_MISMATCH: regenerate with same mappings")
    for payload in (parsed, classification):
        if payload is None:
            continue
        reference = payload.get("lineage")
        if reference is None and allow_legacy:
            continue
        if not isinstance(reference, dict) or reference.get("contract_version") != "offline-lineage-v1":
            raise GdtError("ARTIFACT_LINEAGE_MISSING: regenerate stages or allow legacy explicitly")
        if reference.get("manifest_sha256") != fingerprint:
            raise GdtError("ARTIFACT_LINEAGE_MISMATCH: regenerate derived stages")
    by_source: dict[tuple, list[dict]] = defaultdict(list)
    legacy_members: dict[tuple, list[dict]] = defaultdict(list)
    for container in manifest["containers"]:
        for member in container["members"]:
            row = {**member, "source_zip": container["rel_path"], "source_inner_file": member.get("member_name", "")}
            by_source[source_key(row)].append(row)
            if not row["source_inner_file"]:
                legacy_members[(row.get("artifact_id"), row["source_zip"])].append(row)
    for payload, collection in ((parsed, "declarations"), (classification, "classifications")):
        seen = set()
        for row in (payload or {}).get(collection, []):
            key = source_key(row)
            if key in seen:
                raise GdtError("ARTIFACT_DUPLICATE_SOURCE")
            seen.add(key)
            if allow_legacy and collection == "classifications" and not row.get("source_zip"):
                if sum(k[0] == key[0] for k in by_source) != 1:
                    raise GdtError("ARTIFACT_MEMBERSHIP_MISMATCH: ambiguous legacy classification")
            elif key not in by_source and not (allow_legacy and (key[0], key[1]) in legacy_members):
                raise GdtError("ARTIFACT_MEMBERSHIP_MISMATCH: derived source absent")
    for declaration in (parsed or {}).get("declarations", []):
        candidates = by_source.get(source_key(declaration), [])
        if not candidates and allow_legacy:
            candidates = legacy_members.get((declaration.get("artifact_id"), declaration.get("source_zip")), [])
        if len(candidates) != 1:
            raise GdtError("ARTIFACT_MEMBERSHIP_MISMATCH: parsed source absent or ambiguous")
        expected = candidates[0].get("sha256")
        if expected and declaration.get("source_sha256") != expected:
            raise GdtError("ARTIFACT_HASH_MISMATCH: parsed source changed")
    if not allow_legacy:
        expected_parsed = {key for key, items in by_source.items() if any(m.get("format") == "xml" and m.get("status") == "ok" for m in items)}
        actual_parsed = {source_key(row) for row in (parsed or {}).get("declarations", [])}
        expected_class = {key for key, items in by_source.items() if any(m.get("format") == "xml" for m in items)}
        actual_class = {source_key(row) for row in (classification or {}).get("classifications", [])}
        if expected_parsed != actual_parsed or expected_class != actual_class:
            raise GdtError("ARTIFACT_COVERAGE_MISMATCH: derived stage incomplete")
