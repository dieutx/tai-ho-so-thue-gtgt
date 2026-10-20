"""Shared text and numeric policies for spreadsheet-facing exports."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

from openpyxl.worksheet.worksheet import Worksheet

_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def append_row(sheet: Worksheet, values) -> None:
    """Write strings as literal text, including formulas and control prefixes."""
    clean = [_ILLEGAL.sub("\ufffd", value) if isinstance(value, str) else value for value in values]
    sheet.append(clean)
    for cell, value in zip(sheet[sheet.max_row], clean, strict=False):
        if isinstance(value, str):
            cell.data_type = "s"


def csv_value(value: object) -> object:
    """CSV has no cell types; prefix potentially executable text with apostrophe."""
    if isinstance(value, str) and value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def numeric_cell(value: object, value_type: str | None) -> tuple[object, str | None]:
    """Only typed numbers within Excel's 15-digit precision become numbers."""
    if value is None or value_type not in {"decimal", "integer", "percentage", "number", "numeric"}:
        return value, None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return value, "INVALID_NUMERIC_VALUE"
    if not number.is_finite():
        return value, "NONFINITE_NUMERIC_VALUE"
    significant = len("".join(str(d) for d in number.as_tuple().digits).rstrip("0"))
    if significant > 15 or (number and (number.adjusted() > 307 or number.adjusted() < -307)):
        return value, "EXCEL_PRECISION_PRESERVED_AS_TEXT"
    converted = int(number) if number == number.to_integral_value() else float(number)
    if isinstance(converted, float) and not math.isfinite(converted):
        return value, "EXCEL_PRECISION_PRESERVED_AS_TEXT"
    return converted, None
