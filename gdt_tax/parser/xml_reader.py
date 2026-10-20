"""Đọc XML an toàn và tiện ích lấy giá trị theo XPath.

Dùng chung parser: không resolve entity/DTD, không gọi mạng, có trần bytes/depth.
Namespace được xử lý động (lấy từ root), không strip mù quáng.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from lxml import etree

from ..xml_policy import MAX_XML_BYTES, MAX_XML_DEPTH, MAX_XML_NODES, XmlPolicy, XmlReadError
from ..xml_policy import parse_xml as _parse_xml

_WHITESPACE = re.compile(r"[\s\u00a0]")


def parse_xml(data: bytes) -> etree._Element:
    """Parse XML an toàn; ném :class:`XmlReadError` thay vì để lỗi lọt ra."""
    return _parse_xml(data, XmlPolicy(MAX_XML_BYTES, MAX_XML_DEPTH, MAX_XML_NODES))


def namespace_map(root: etree._Element) -> dict[str, str]:
    """Map tiền tố XPath cho namespace mặc định của root (nếu có)."""
    uri = etree.QName(root).namespace
    return {"n": uri} if uri else {}


def main_scope(root: etree._Element) -> tuple[etree._Element, etree._Element]:
    """Select a single main declaration and its metadata, excluding appendices."""
    roots = {'HSoThueDTu', 'TBao', 'TKhai'}
    if localname(root) not in roots:
        documents = [node for node in root.iterdescendants() if localname(node) in roots
                     and not any(localname(parent) in roots for parent in node.iterancestors())]
        if len(documents) > 1:
            raise XmlReadError('AMBIGUOUS_MAIN_DECLARATION')
        if documents:
            root = documents[0]
    uri = etree.QName(root).namespace
    candidates = [node for node in root.iter() if isinstance(node.tag, str)
                  and etree.QName(node).namespace == uri and localname(node) == 'HSoKhaiThue'
                  and not in_appendix(node)]
    if len(candidates) > 1:
        raise XmlReadError('AMBIGUOUS_MAIN_DECLARATION')
    primary = candidates[0] if candidates else root
    common = [node for node in primary.iter() if isinstance(node.tag, str)
              and etree.QName(node).namespace == uri and localname(node) == 'TTinChung'
              and not in_appendix(node)]
    if len(common) > 1:
        raise XmlReadError('AMBIGUOUS_DECLARATION_METADATA')
    return primary, common[0] if common else primary


def in_appendix(node: etree._Element) -> bool:
    return any((localname(parent) or '').casefold().startswith(('pluc', 'bangke', 'appendix'))
               for parent in node.iterancestors())


def localname(element: etree._Element) -> str | None:
    if not isinstance(element.tag, str):
        return None
    return etree.QName(element).localname


def find_text(root: etree._Element, path: str, ns: dict[str, str]) -> str | None:
    """Trả text đầu tiên khớp ``path`` (đã strip), hoặc ``None``.

    XML có thể không namespace (ví dụ ``TBao``); khi đó bỏ tiền tố ``n:`` khỏi
    đường dẫn để khớp tên thẻ trần thay vì trả ``None``.
    """
    effective = path if ns else path.replace("n:", "")
    try:
        element = root.find(effective, ns or None)
    except (SyntaxError, KeyError, etree.XPathError):
        return None
    if element is None:
        return None
    text = "".join(element.itertext()).strip()
    return text or None


def find_first(root: etree._Element, paths, ns: dict[str, str]) -> tuple[str | None, str | None]:
    """Trả ``(giá trị, xpath khớp)`` cho đường dẫn đầu tiên có giá trị."""
    for path in paths:
        value = find_text(root, path, ns)
        if value is not None:
            return value, path
    return None, None


def _split_decimal(text: str) -> str:
    """Chuẩn hóa dấu phân cách của một chuỗi số về dạng ``1234567.89``."""
    has_comma = "," in text
    has_dot = "." in text
    if has_comma and has_dot:
        # Dấu xuất hiện sau cùng là dấu thập phân (1.234,56 hoặc 1,234.56).
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")
    if has_comma or has_dot:
        separator = "," if has_comma else "."
        parts = text.split(separator)
        if len(parts) > 2:
            # Xuất hiện nhiều lần ⇒ toàn là dấu phân cách nghìn.
            return "".join(parts)
        # Một lần: theo sau đúng 3 chữ số ⇒ phân cách nghìn (1.234 / 1,234).
        if len(parts[1]) == 3 and len(parts[0]) >= 1:
            return "".join(parts)
        return f"{parts[0]}.{parts[1]}" if parts[1] else parts[0]
    return text


def normalize_number(raw: str | None) -> tuple[str | None, str | None]:
    """Chuẩn hóa số: bỏ dấu phân cách nghìn, giữ dấu trừ và phần thập phân.

    Trả ``(value, warning)``. Không biến giá trị lỗi thành 0 — trả ``None`` kèm
    ``PARSE_VALUE_ERROR`` để giữ ``raw_value`` phục vụ kiểm tra.
    """
    if raw is None:
        return None, None
    text = _WHITESPACE.sub("", raw.strip())
    if not text:
        return None, None
    sign = ""
    if text[0] in "+-":
        sign, text = text[0], text[1:]
    if not text or not text.replace(",", "").replace(".", "").isdigit():
        return None, "PARSE_VALUE_ERROR"
    cleaned = sign + _split_decimal(text)
    try:
        Decimal(cleaned)
    except InvalidOperation:
        return None, "PARSE_VALUE_ERROR"
    return cleaned, None


def is_zero(value: str | None) -> bool:
    if value is None:
        return False
    try:
        return Decimal(value) == 0
    except InvalidOperation:
        return False


__all__ = [
    "MAX_XML_BYTES",
    "MAX_XML_DEPTH",
    "MAX_XML_NODES",
    "XmlReadError",
    "find_first",
    "find_text",
    "is_zero",
    "localname",
    "main_scope",
    "in_appendix",
    "namespace_map",
    "normalize_number",
    "parse_xml",
]
