"""Tầng parser tờ khai (stage 04).

Khung parser tách khỏi mapping mẫu biểu: :mod:`gdt_tax.parser.registry` nạp mapping
từ ``gdt_tax/form_mappings``, :mod:`gdt_tax.parser.extract` trích metadata chung + chỉ tiêu
tổng hợp kèm provenance, không hard-code mẫu trong code.
"""

from __future__ import annotations

from .extract import PARSER_VERSION, SCHEMA_VERSION, extract_declaration
from .models import Indicator, ParsedDeclaration, Period, Taxpayer
from .registry import FormMapping, MappingRegistry, load_registry
from .xml_reader import XmlReadError, normalize_number, parse_xml

__all__ = [
    "FormMapping",
    "Indicator",
    "MappingRegistry",
    "PARSER_VERSION",
    "ParsedDeclaration",
    "Period",
    "SCHEMA_VERSION",
    "Taxpayer",
    "XmlReadError",
    "extract_declaration",
    "load_registry",
    "normalize_number",
    "parse_xml",
]
