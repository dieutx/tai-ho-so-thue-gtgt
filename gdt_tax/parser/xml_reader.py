"""Đọc XML an toàn và tiện ích lấy giá trị theo XPath.

Dùng chung parser: không resolve entity/DTD, không gọi mạng, có trần bytes/depth.
Namespace được xử lý động (lấy từ root), không strip mù quáng.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from lxml import etree

MAX_XML_BYTES = 32 * 1024 * 1024
MAX_XML_DEPTH = 100
MAX_XML_NODES = 200_000

_WHITESPACE = re.compile(r"[\s\u00a0]")


class XmlReadError(Exception):
    """XML không đọc được (lỗi cú pháp, quá lớn, quá sâu...)."""


def parse_xml(data: bytes) -> etree._Element:
    """Parse XML an toàn; ném :class:`XmlReadError` thay vì để lỗi lọt ra."""
    if len(data) > MAX_XML_BYTES:
        raise XmlReadError("XML_TOO_LARGE")
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        recover=False,
    )
    try:
        root = etree.fromstring(data, parser=parser)
    except (etree.XMLSyntaxError, ValueError, TypeError) as error:
        raise XmlReadError(f"INVALID_XML: {error}") from error
    if root is None:
        raise XmlReadError("EMPTY_XML")
    return root


def namespace_map(root: etree._Element) -> dict[str, str]:
    """Map tiền tố XPath cho namespace mặc định của root (nếu có)."""
    default = root.nsmap.get(None)
    return {"n": default} if default else {}


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
    "namespace_map",
    "normalize_number",
    "parse_xml",
]
