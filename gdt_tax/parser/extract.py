"""Trích xuất tờ khai: metadata chung + chỉ tiêu tổng hợp, có provenance.

Hai chế độ:

* **Có mapping** — chỉ tiêu được gán ``canonical_name`` theo registry, trạng thái
  ``MAPPED``.
* **Chưa mapping** — vẫn trích xuất mọi mã chỉ tiêu tìm được nhưng trạng thái
  ``NEED_MAPPING`` và ``canonical_name = None``. **Không** suy đoán ý nghĩa.

Quét chỉ tiêu ưu tiên node ``CTieuTKhaiChinh`` (chỉ tiêu tổng hợp trên tờ khai
chính); **không** đi vào các bảng kê chi tiết (``PLuc``, ``BangKe*``). Với node
lồng nhau (ví dụ ``GiaTriVaThueGTGTHHDVMuaVao``) chỉ lấy các node con trực tiếp
có tên dạng mã chỉ tiêu, không lấy cấp sâu hơn.
"""

from __future__ import annotations

import re

from lxml import etree

from .models import Indicator, ParsedDeclaration, Period, Taxpayer
from .registry import FormMapping, MappingRegistry
from .xml_reader import (
    XmlReadError,
    find_first,
    find_text,
    in_appendix,
    localname,
    main_scope,
    namespace_map,
    normalize_number,
    parse_xml,
)

PARSER_VERSION = "declaration-parser-v3"
SCHEMA_VERSION = "parsed-declaration-v1"

#: Node chứa chỉ tiêu tổng hợp trên tờ khai chính (không phải bảng kê chi tiết).
MAIN_INDICATOR_NODES = ("CTieuTKhaiChinh",)
#: Tên node được xem là mã chỉ tiêu: ct21, ct23a, ctB12, ctA1, ...
_INDICATOR_CODE = re.compile(r"^ct[A-Za-z]?\d+[a-z]?$")
#: Tên node không phải chỉ tiêu dù nằm trong nhóm (nhãn/đơn vị/mô tả).
_NON_INDICATOR = re.compile(r"(ten|ma_|donVi|moTa|ghiChu|ky|Header|NghiaVu|tong)", re.IGNORECASE)

_TAX_TYPE_HINTS = (
    ("GTGT", ("giá trị gia tăng", "gtgt")),
    ("TNCN", ("thu nhập cá nhân", "tncn")),
    ("TNDN", ("thu nhập doanh nghiệp", "tndn")),
    ("FCT", ("nhà thầu", "ntnn")),
    ("MON_BAI", ("môn bài", "lpmb")),
    ("TAI_NGUYEN", ("tài nguyên",)),
)


def _guess_tax_type(form_name: str | None) -> str | None:
    if not form_name:
        return None
    lowered = form_name.lower()
    for group, terms in _TAX_TYPE_HINTS:
        if any(term in lowered for term in terms):
            return group
    return None


def _xpath_of(element: etree._Element) -> str:
    parts: list[str] = []
    current = element
    while current is not None and isinstance(current.tag, str):
        name = localname(current)
        if name is None:
            break
        parts.append(name)
        current = current.getparent()
    return "/" + "/".join(reversed(parts))


def _ns_path(path: str, has_ns: bool) -> str:
    """Thêm tiền tố namespace vào từng đoạn của XPath mapping khi cần."""
    if not has_ns:
        return path
    return "/".join(segment if segment.startswith("n:") else f"n:{segment}"
                     for segment in path.split("/"))


def _normalize_mapped_value(raw: str, datatype: str) -> tuple[str | None, str | None]:
    """Chuẩn hóa theo kiểu khai trong mapping, không ép nhãn text thành số."""
    if datatype == "string":
        value = raw.strip()
        return (value or None), None
    return normalize_number(raw)


def _period_parts(raw: str | None, period_type: str | None) -> tuple[int | None, int | None, int | None]:
    """Tách năm/tháng/quý khi kiểu kỳ và định dạng đủ rõ; giữ ``raw`` nguyên bản."""
    if not raw or not period_type:
        return None, None, None
    value = raw.strip()
    kind = period_type.upper()
    if kind == "Y" and re.fullmatch(r"\d{4}", value):
        return int(value), None, None
    month_match = re.fullmatch(r"(\d{1,2})/(\d{4})", value)
    if kind == "M" and month_match:
        month = int(month_match.group(1))
        if 1 <= month <= 12:
            return int(month_match.group(2)), month, None
    quarter_match = re.fullmatch(r"(?:Q|QUÝ\s*)?(\d)/(\d{4})", value, re.IGNORECASE)
    if kind == "Q" and quarter_match:
        quarter = int(quarter_match.group(1))
        if 1 <= quarter <= 4:
            return int(quarter_match.group(2)), None, quarter
    return None, None, None


def _collect_indicators(
    root: etree._Element,
    mapping: FormMapping | None,
    ns: dict[str, str],
) -> list[Indicator]:
    indicators: list[Indicator] = []
    seen: set[str] = set()
    if mapping is not None:
        for field in mapping.fields.values():
            code = field.indicator_code
            if code in seen:
                continue
            path = field.xpath or code
            raw = find_text(root, ".//" + _ns_path(path, bool(ns)), ns)
            if raw is None:
                # Mapping có nhưng XML không có chỉ tiêu ⇒ giữ NULL, ghi warning.
                indicators.append(
                    Indicator(
                        code=code,
                        value=None,
                        raw_value=None,
                        value_type=field.datatype,
                        xpath=".//" + path,
                        canonical_name=field.canonical_name,
                        display_name=field.display_name,
                        official_indicator_code=code,
                        official_indicator_name=field.official_indicator_name,
                        status="MAPPED",
                        warnings=["MISSING_IN_XML"],
                    )
                )
                seen.add(code)
                continue
            value, warning = _normalize_mapped_value(raw, field.datatype)
            indicators.append(
                Indicator(
                    code=code,
                    value=value,
                    raw_value=raw,
                    value_type=field.datatype,
                    xpath=".//" + path,
                    canonical_name=field.canonical_name,
                    display_name=field.display_name,
                    official_indicator_code=code,
                    official_indicator_name=field.official_indicator_name,
                    status="MAPPED",
                    warnings=[warning] if warning else [],
                )
            )
            seen.add(code)
    # Bổ sung chỉ tiêu chưa có trong mapping (giữ NEED_MAPPING, không đoán).
    for node_name in MAIN_INDICATOR_NODES:
        for container in root.iter():
            if (localname(container) != node_name or in_appendix(container)
                    or etree.QName(container).namespace != etree.QName(root).namespace):
                continue
            for child in container:
                _collect_from(child, indicators, seen, mapping, etree.QName(root).namespace)
    return indicators


def _collect_from(
    element: etree._Element,
    indicators: list[Indicator],
    seen: set[str],
    mapping: FormMapping | None,
    namespace_uri: str | None,
) -> None:
    name = localname(element)
    if name is None or name in seen:
        return
    if etree.QName(element).namespace != namespace_uri:
        return
    if _INDICATOR_CODE.match(name) and not _NON_INDICATOR.search(name):
        seen.add(name)
        raw = "".join(element.itertext()).strip()
        value, warning = normalize_number(raw or None)
        field = mapping.field_for_code(name) if mapping is not None else None
        warnings = [warning] if warning else []
        indicators.append(
            Indicator(
                code=name,
                value=value,
                raw_value=raw or None,
                value_type="decimal",
                xpath=_xpath_of(element),
                canonical_name=field.canonical_name if field else None,
                display_name=field.display_name if field else None,
                official_indicator_code=name,
                official_indicator_name=field.official_indicator_name if field else None,
                status="MAPPED" if field else "NEED_MAPPING",
                warnings=warnings,
            )
        )
        return
    # Node nhóm: chỉ đi xuống các node con trực tiếp một cấp.
    if _NON_INDICATOR.search(name):
        return
    for child in element:
        _collect_from(child, indicators, seen, mapping, namespace_uri)


def extract_declaration(
    data: bytes,
    *,
    artifact_id: str | None = None,
    source_zip: str | None = None,
    source_inner_file: str | None = None,
    source_sha256: str | None = None,
    registry: MappingRegistry | None = None,
) -> ParsedDeclaration:
    """Parse một XML thành :class:`ParsedDeclaration`; lỗi trả ``status='error'``."""
    try:
        root = parse_xml(data)
        root, metadata = main_scope(root)
    except XmlReadError as error:
        return ParsedDeclaration(
            schema_version=SCHEMA_VERSION,
            parser_version=PARSER_VERSION,
            artifact_id=artifact_id,
            source_zip=source_zip,
            source_inner_file=source_inner_file,
            source_sha256=source_sha256,
            form_code=None,
            form_name=None,
            form_version=None,
            tax_type_hint=None,
            filing_type=None,
            supplement_number=None,
            taxpayer=Taxpayer(),
            period=Period(),
            indicators=[],
            status="error",
            error=str(error),
        )

    ns = namespace_map(root)
    form_code, _ = find_first(metadata, (".//n:maTKhai", ".//n:MSo"), ns)
    form_name, _ = find_first(metadata, (".//n:tenTKhai", ".//n:Ten"), ns)
    form_version, _ = find_first(metadata, (".//n:pbanTKhaiXML", ".//n:PBan"), ns)
    filing_type, _ = find_first(metadata, (".//n:loaiTKhai",), ns)
    supplement, _ = find_first(metadata, (".//n:soLan",), ns)
    tax_code, _ = find_first(metadata, (".//n:mst", ".//n:MST"), ns)
    taxpayer_name, _ = find_first(metadata, (".//n:tenNNT", ".//n:TNNT"), ns)
    address, _ = find_first(metadata, (".//n:dchiNNT", ".//n:DDanh"), ns)
    period_raw, _ = find_first(metadata, (".//n:kyKKhai",), ns)
    period_type, _ = find_first(metadata, (".//n:kieuKy",), ns)
    period_from, _ = find_first(metadata, (".//n:kyKKhaiTuNgay",), ns)
    period_to, _ = find_first(metadata, (".//n:kyKKhaiDenNgay",), ns)
    period_year, period_month, period_quarter = _period_parts(period_raw, period_type)

    mapping = registry.lookup(form_code, form_version) if registry is not None else None
    indicators = _collect_indicators(root, mapping, ns)
    warnings: list[str] = []
    status = "MAPPED" if mapping is not None else "NEED_MAPPING"
    if mapping is None and (form_code or form_name):
        warnings.append("MAPPING_NOT_FOUND")
    if not form_code:
        warnings.append("MISSING_FORM_CODE")

    return ParsedDeclaration(
        schema_version=SCHEMA_VERSION,
        parser_version=PARSER_VERSION,
        artifact_id=artifact_id,
        source_zip=source_zip,
        source_inner_file=source_inner_file,
        source_sha256=source_sha256,
        form_code=form_code,
        form_name=form_name,
        form_version=form_version,
        tax_type_hint=mapping.tax_type if mapping else _guess_tax_type(form_name),
        filing_type=filing_type,
        supplement_number=supplement,
        taxpayer=Taxpayer(tax_code=tax_code, name=taxpayer_name, address=address),
        period=Period(
            raw=period_raw,
            period_type=period_type,
            year=period_year,
            month=period_month,
            quarter=period_quarter,
            period_from=period_from,
            period_to=period_to,
        ),
        indicators=indicators,
        status=status,
        mapping_id=mapping.mapping_id if mapping else None,
        mapping_version=mapping.mapping_version if mapping else None,
        warnings=warnings,
    )


__all__ = [
    "MAIN_INDICATOR_NODES",
    "PARSER_VERSION",
    "SCHEMA_VERSION",
    "extract_declaration",
]
