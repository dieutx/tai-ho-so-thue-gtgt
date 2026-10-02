"""Kiểu dữ liệu của tầng parser (stage 04).

Tách rõ *chỉ tiêu chính thức* (mã chỉ tiêu trong XML) khỏi *canonical field*
(tên chuẩn hóa sau khi mapping được xác nhận). Khi chưa có mapping, chỉ tiêu vẫn
được trích xuất nhưng mang ``canonical_name = None`` và ``status = NEED_MAPPING``
— **không** tự suy đoán ý nghĩa từ tên thẻ.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Indicator:
    """Một chỉ tiêu tổng hợp (hoặc chỉ tiêu con) đọc từ XML.

    ``value`` giữ dạng chuỗi đã chuẩn hóa dấu phân cách nghìn, hoặc ``None`` khi
    chỉ tiêu rỗng/không có — phân biệt rõ NULL với ``"0"``.
    """

    code: str
    value: str | None
    raw_value: str | None
    value_type: str
    xpath: str
    canonical_name: str | None = None
    display_name: str | None = None
    official_indicator_code: str | None = None
    official_indicator_name: str | None = None
    status: str = "NEED_MAPPING"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Taxpayer:
    tax_code: str | None = None
    name: str | None = None
    address: str | None = None


@dataclass
class Period:
    raw: str | None = None
    period_type: str | None = None
    year: int | None = None
    month: int | None = None
    quarter: int | None = None
    period_from: str | None = None
    period_to: str | None = None


@dataclass
class ParsedDeclaration:
    """Kết quả parse một XML tờ khai, có version và provenance đầy đủ."""

    schema_version: str
    parser_version: str
    artifact_id: str | None
    source_zip: str | None
    source_inner_file: str | None
    source_sha256: str | None
    form_code: str | None
    form_name: str | None
    form_version: str | None
    tax_type_hint: str | None
    filing_type: str | None
    supplement_number: str | None
    taxpayer: Taxpayer
    period: Period
    indicators: list[Indicator]
    status: str
    mapping_id: str | None = None
    mapping_version: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def indicator(self, code: str) -> Indicator | None:
        for item in self.indicators:
            if item.code == code:
                return item
        return None


__all__ = ["Indicator", "ParsedDeclaration", "Period", "Taxpayer"]
