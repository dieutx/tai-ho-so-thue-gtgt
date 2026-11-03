"""Form Mapping Registry — nạp mapping đóng gói cùng ``gdt_tax``.

Parser **không** hard-code mẫu biểu. Mỗi phiên bản tờ khai có một file mapping
(JSON, không cần dependency ngoài) khai báo ``form_code`` + ``form_version`` và
ánh xạ canonical field → mã chỉ tiêu. Khi chưa có mapping, hệ thống trả
``UNMAPPED_FORM``/``NEED_MAPPING`` thay vì đoán.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

LOGGER_NAME = "gdt_tax.parser.registry"

#: Thư mục mapping mặc định nằm trong package để cả source checkout và wheel
#: đều dùng được. CLI vẫn cho phép ``--forms-dir`` để nạp registry riêng.
DEFAULT_FORMS_DIR = Path(__file__).resolve().parents[1] / "form_mappings"

REQUIRED_KEYS = ("mapping_id", "mapping_version", "form_code", "fields")


@dataclass
class FieldMapping:
    canonical_name: str
    indicator_code: str
    display_name: str | None = None
    official_indicator_name: str | None = None
    datatype: str = "decimal"
    #: XPath chính thức (không tiền tố namespace). Nếu có, extractor ưu tiên dùng
    #: đúng đường dẫn này thay vì dò theo mã chỉ tiêu.
    xpath: str | None = None


@dataclass
class FormMapping:
    mapping_id: str
    mapping_version: str
    form_code: str
    form_version: str | None = None
    verified_form_versions: tuple[str, ...] = ()
    tax_type: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    detect_root: str | None = None
    detect_namespace: str | None = None
    fields: dict[str, FieldMapping] = field(default_factory=dict)
    source_path: str | None = None

    def field_for_code(self, indicator_code: str) -> FieldMapping | None:
        for item in self.fields.values():
            if item.indicator_code == indicator_code:
                return item
        return None


class MappingRegistry:
    """Tập mapping đã nạp, tra theo ``(form_code, form_version)``."""

    def __init__(self) -> None:
        #: Danh sách mapping theo file cấu hình (không nhân bản theo version alias).
        self._mappings: list[FormMapping] = []
        #: Mapping theo đúng ``(form_code, form_version)``.
        self._by_key: dict[tuple[str, str], FormMapping] = {}
        #: Mapping khai ``form_version = null`` (áp cho mọi phiên bản của mã mẫu).
        self._by_code_any: dict[str, FormMapping] = {}

    def add(self, mapping: FormMapping) -> None:
        self._mappings.append(mapping)
        if mapping.verified_form_versions:
            for version in mapping.verified_form_versions:
                self._by_key[(mapping.form_code, version)] = mapping
        elif mapping.form_version is None:
            self._by_code_any[mapping.form_code] = mapping
        else:
            self._by_key[(mapping.form_code, mapping.form_version)] = mapping

    def lookup(self, form_code: str | None, form_version: str | None) -> FormMapping | None:
        if not form_code:
            return None
        if form_version is not None:
            exact = self._by_key.get((form_code, form_version))
            if exact is not None:
                return exact
        # Chỉ dùng bản "mọi phiên bản" khi mapping đó khai tường minh
        # ``form_version = null``. Không tự áp bản của version khác cho version
        # chưa xác nhận (spec §45).
        return self._by_code_any.get(form_code)

    def __len__(self) -> int:
        return len(self._mappings)

    def mappings(self) -> list[FormMapping]:
        return list(self._mappings)


def _parse_mapping(payload: dict, source: str) -> FormMapping:
    missing = [key for key in REQUIRED_KEYS if not payload.get(key)]
    if missing:
        raise ValueError(f"{source}: thiếu trường {', '.join(missing)}")
    fields: dict[str, FieldMapping] = {}
    for canonical, spec in (payload.get("fields") or {}).items():
        if not isinstance(spec, dict) or not spec.get("indicator_code"):
            raise ValueError(f"{source}: field {canonical!r} thiếu indicator_code")
        fields[canonical] = FieldMapping(
            canonical_name=str(spec.get("canonical_name") or canonical),
            indicator_code=str(spec["indicator_code"]),
            display_name=spec.get("display_name"),
            official_indicator_name=spec.get("official_indicator_name"),
            datatype=str(spec.get("datatype") or "decimal"),
            xpath=spec.get("xpath"),
        )
    detect = payload.get("detect") or {}
    raw_versions = payload.get("verified_form_versions") or []
    if not isinstance(raw_versions, list) or not all(
        isinstance(version, str) and version.strip() for version in raw_versions
    ):
        raise ValueError(f"{source}: verified_form_versions phải là danh sách chuỗi")
    if payload.get("form_version") and raw_versions:
        raise ValueError(f"{source}: chỉ dùng form_version hoặc verified_form_versions")
    return FormMapping(
        mapping_id=str(payload["mapping_id"]),
        mapping_version=str(payload["mapping_version"]),
        form_code=str(payload["form_code"]),
        form_version=str(payload["form_version"]) if payload.get("form_version") else None,
        verified_form_versions=tuple(raw_versions),
        tax_type=payload.get("tax_type"),
        effective_from=payload.get("effective_from"),
        effective_to=payload.get("effective_to"),
        detect_root=detect.get("root"),
        detect_namespace=detect.get("namespace"),
        fields=fields,
        source_path=source,
    )


def load_registry(
    forms_dir: str | Path | None = None,
    logger: logging.Logger | None = None,
) -> MappingRegistry:
    """Nạp mọi ``*.json`` trong thư mục mapping; file lỗi bị bỏ qua và ghi log."""
    log = logger or logging.getLogger(LOGGER_NAME)
    directory = Path(forms_dir) if forms_dir is not None else DEFAULT_FORMS_DIR
    registry = MappingRegistry()
    if not directory.is_dir():
        log.debug("Chưa có thư mục mapping: %s", directory)
        return registry
    for path in sorted(directory.rglob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            log.warning("Bỏ qua mapping lỗi %s: %s", path, error)
            continue
        if not isinstance(payload, dict):
            log.warning("Bỏ qua mapping không phải object: %s", path)
            continue
        try:
            registry.add(_parse_mapping(payload, str(path)))
        except ValueError as error:
            log.warning("%s", error)
    log.debug("Đã nạp %s mapping từ %s", len(registry), directory)
    return registry


__all__ = [
    "DEFAULT_FORMS_DIR",
    "FieldMapping",
    "FormMapping",
    "MappingRegistry",
    "load_registry",
]
