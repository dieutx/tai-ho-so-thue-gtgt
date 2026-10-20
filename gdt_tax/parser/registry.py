"""Form Mapping Registry — nạp mapping đóng gói cùng ``gdt_tax``.

Parser **không** hard-code mẫu biểu. Mỗi phiên bản tờ khai có một file mapping
(JSON, không cần dependency ngoài) khai báo ``form_code`` + ``form_version`` và
ánh xạ canonical field → mã chỉ tiêu. Khi chưa có mapping, hệ thống trả
``UNMAPPED_FORM``/``NEED_MAPPING`` thay vì đoán.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from lxml import etree

from ..errors import GdtError

LOGGER_NAME = "gdt_tax.parser.registry"

#: Thư mục mapping mặc định nằm trong package để cả source checkout và wheel
#: đều dùng được. CLI vẫn cho phép ``--forms-dir`` để nạp registry riêng.
DEFAULT_FORMS_DIR = Path(__file__).resolve().parents[1] / "form_mappings"

REQUIRED_KEYS = ("mapping_id", "mapping_version", "form_code", "fields")


class MappingError(GdtError, ValueError):
    """Invalid or ambiguous mapping configuration."""


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
    numeric_format: str = 'auto'
    required: bool = False


@dataclass
class FormMapping:
    mapping_id: str
    mapping_version: str
    form_code: str
    form_version: str | None = None
    tax_type: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    detect_root: str | None = None
    detect_namespace: str | None = None
    fields: dict[str, FieldMapping] = field(default_factory=dict)
    source_path: str | None = None
    supported_versions: tuple[str, ...] = ()
    source_sha256: str | None = None

    def matches_profile(self, root_name: str | None, namespace: str | None, as_of: date | None = None) -> bool:
        if self.detect_root and root_name != self.detect_root:
            return False
        if self.detect_namespace and namespace != self.detect_namespace:
            return False
        return self._date_matches(as_of)

    def _date_matches(self, as_of: date | None) -> bool:
        if self.effective_from or self.effective_to:
            if as_of is None:
                return False
            if self.effective_from and as_of < date.fromisoformat(self.effective_from):
                return False
            if self.effective_to and as_of > date.fromisoformat(self.effective_to):
                return False
        return True

    def matches_document(self, root: etree._Element, as_of: date | None = None) -> bool:
        if self.detect_namespace and etree.QName(root).namespace != self.detect_namespace:
            return False
        if self.detect_root and not any(
            isinstance(node.tag, str) and etree.QName(node).localname == self.detect_root
            and etree.QName(node).namespace == etree.QName(root).namespace
            for node in [root, *root.iterancestors()]
        ):
            return False
        return self._date_matches(as_of)

    @property
    def fingerprint(self) -> str:
        payload = asdict(self)
        payload.pop('source_path', None)
        payload.pop('source_sha256', None)
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def field_for_code(self, indicator_code: str) -> FieldMapping | None:
        for item in self.fields.values():
            if item.indicator_code == indicator_code:
                return item
        return None


class MappingRegistry:
    """Tập mapping đã nạp, tra theo ``(form_code, form_version)``."""

    def __init__(self) -> None:
        #: Mapping theo đúng ``(form_code, form_version)``.
        self._by_key: dict[tuple[str, str], FormMapping] = {}
        #: Mapping khai ``form_version = null`` (áp cho mọi phiên bản của mã mẫu).
        self._by_code_any: dict[str, FormMapping] = {}
        self.diagnostics: list[str] = []
        self.overrides: list[dict[str, str]] = []

    def add(self, mapping: FormMapping, *, replace: bool = False) -> None:
        previous = (self._by_code_any.get(mapping.form_code) if mapping.form_version is None
                    else self._by_key.get((mapping.form_code, mapping.form_version)))
        if any(item.mapping_id == mapping.mapping_id and item is not previous for item in self.mappings()):
            raise MappingError(f'DUPLICATE_MAPPING_ID: {mapping.mapping_id}')
        if previous is not None:
            if not replace:
                raise MappingError(f'DUPLICATE_MAPPING: {mapping.form_code}/{mapping.form_version}')
            self.overrides.append({'previous': previous.mapping_id, 'replacement': mapping.mapping_id})
        if mapping.form_version is None:
            self._by_code_any[mapping.form_code] = mapping
        else:
            self._by_key[(mapping.form_code, mapping.form_version)] = mapping

    def lookup(self, form_code: str | None, form_version: str | None) -> FormMapping | None:
        if not form_code:
            return None
        if form_version is not None:
            exact = self._by_key.get((form_code, form_version))
            if exact is not None:
                return exact if not exact.supported_versions or form_version in exact.supported_versions else None
        # Chỉ dùng bản "mọi phiên bản" khi mapping đó khai tường minh
        # ``form_version = null``. Không tự áp bản của version khác cho version
        # chưa xác nhận (spec §45).
        any_version = self._by_code_any.get(form_code)
        if any_version and any_version.supported_versions and form_version not in any_version.supported_versions:
            return None
        return any_version

    @property
    def fingerprint(self) -> str:
        hashes = sorted(mapping.fingerprint for mapping in self.mappings())
        return hashlib.sha256('\n'.join(hashes).encode()).hexdigest()

    def __len__(self) -> int:
        return len(self._by_key) + len(self._by_code_any)

    def mappings(self) -> list[FormMapping]:
        return [*self._by_key.values(), *self._by_code_any.values()]


def _parse_mapping(payload: dict, source: str) -> FormMapping:
    missing = [key for key in REQUIRED_KEYS if not payload.get(key)]
    if missing:
        raise MappingError(f"{source}: thiếu trường {', '.join(missing)}")
    if any(not isinstance(payload[key], str) for key in REQUIRED_KEYS[:3]):
        raise MappingError(f'{source}: mapping identifiers must be strings')
    if payload.get('tax_type') is not None and not isinstance(payload['tax_type'], str):
        raise MappingError(f'{source}: tax_type must be a string')
    if not isinstance(payload['fields'], dict) or len(payload['fields']) > 5000:
        raise MappingError(f'{source}: fields must be an object with at most 5000 entries')
    default_format = payload.get('numeric_format', 'auto')
    versions = payload.get('supported_versions', [])
    if not isinstance(versions, list) or any(not isinstance(v, str) or not v for v in versions):
        raise MappingError(f'{source}: supported_versions must be strings')
    version = payload.get('form_version')
    if version is not None and (not isinstance(version, str) or not version):
        raise MappingError(f'{source}: form_version must be nonempty string or null')
    for key in ['effective_from', 'effective_to']:
        if payload.get(key) is not None:
            try:
                date.fromisoformat(payload[key])
            except (ValueError, TypeError) as error:
                raise MappingError(f'{source}: invalid {key}') from error
    if payload.get('effective_from') and payload.get('effective_to') and payload['effective_from'] > payload['effective_to']:
        raise MappingError(f'{source}: reversed effective date range')
    fields: dict[str, FieldMapping] = {}
    codes: set[str] = set()
    for canonical, spec in (payload.get("fields") or {}).items():
        if not isinstance(spec, dict) or not spec.get("indicator_code"):
            raise MappingError(f"{source}: field {canonical!r} thiếu indicator_code")
        code = spec['indicator_code']
        datatype = spec.get('datatype', 'decimal')
        numeric_format = spec.get('numeric_format', default_format)
        path = spec.get('xpath')
        if not isinstance(code, str) or code in codes:
            raise MappingError(f'{source}: indicator_code must be unique strings')
        codes.add(code)
        if not isinstance(datatype, str) or datatype not in {'string', 'integer', 'decimal', 'percentage'}:
            raise MappingError(f'{source}: unsupported datatype')
        if not isinstance(numeric_format, str) or numeric_format not in {'auto', 'xml_decimal', 'vi', 'en'}:
            raise MappingError(f'{source}: unsupported numeric_format')
        if path is not None and (not isinstance(path, str) or len(path) > 512 or not all(
            re.fullmatch(r'[A-Za-z_][\w.-]*(?:\[[1-9]\d*\])?', segment) for segment in path.split('/')
        )):
            raise MappingError(f'{source}: invalid relative element XPath')
        if not isinstance(spec.get('required', False), bool):
            raise MappingError(f'{source}: required must be boolean')
        if any(spec.get(name) is not None and not isinstance(spec[name], str)
               for name in ['canonical_name', 'display_name', 'official_indicator_name']):
            raise MappingError(f'{source}: field labels must be strings')
        fields[canonical] = FieldMapping(
            canonical_name=str(spec.get("canonical_name") or canonical),
            indicator_code=str(spec["indicator_code"]),
            display_name=spec.get("display_name"),
            official_indicator_name=spec.get("official_indicator_name"),
            datatype=str(spec.get("datatype") or "decimal"),
            xpath=spec.get("xpath"),
            numeric_format=numeric_format,
            required=spec.get('required', False),
        )
    detect = {} if payload.get('detect') is None else payload['detect']
    if not isinstance(detect, dict) or any(value is not None and not isinstance(value, str) for value in detect.values()):
        raise MappingError(f'{source}: detect must contain string values')
    return FormMapping(
        mapping_id=str(payload["mapping_id"]),
        mapping_version=str(payload["mapping_version"]),
        form_code=str(payload["form_code"]),
        form_version=str(payload["form_version"]) if payload.get("form_version") else None,
        tax_type=payload.get("tax_type"),
        effective_from=payload.get("effective_from"),
        effective_to=payload.get("effective_to"),
        detect_root=detect.get("root"),
        detect_namespace=detect.get("namespace"),
        fields=fields,
        source_path=source,
        supported_versions=tuple(versions),
        source_sha256=hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    )


def load_registry(
    forms_dir: str | Path | None = None,
    logger: logging.Logger | None = None,
    *, strict: bool | None = None, allow_override: bool = False,
) -> MappingRegistry:
    """Nạp mọi ``*.json`` trong thư mục mapping; file lỗi bị bỏ qua và ghi log."""
    log = logger or logging.getLogger(LOGGER_NAME)
    directory = Path(forms_dir) if forms_dir is not None else DEFAULT_FORMS_DIR
    registry = MappingRegistry()
    strict = forms_dir is None if strict is None else strict
    def reject(message: str) -> None:
        registry.diagnostics.append(message)
        if strict:
            raise MappingError(message)
        log.warning('%s', message)
    if not directory.is_dir():
        reject(f'MAPPING_DIRECTORY_MISSING: {directory}')
        return registry
    for path in sorted(directory.rglob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            if path.stat().st_size > 1024 * 1024:
                raise MappingError('MAPPING_TOO_LARGE')
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            reject(f'MAPPING_INVALID: {path.name}: {type(error).__name__}')
            continue
        if not isinstance(payload, dict):
            reject(f'MAPPING_INVALID: {path.name}: expected object')
            continue
        try:
            registry.add(_parse_mapping(payload, str(path)), replace=allow_override)
        except ValueError as error:
            reject(str(error))
    log.debug("Đã nạp %s mapping từ %s", len(registry), directory)
    return registry


__all__ = [
    "DEFAULT_FORMS_DIR",
    "FieldMapping",
    "FormMapping",
    "MappingRegistry",
    "load_registry",
]
