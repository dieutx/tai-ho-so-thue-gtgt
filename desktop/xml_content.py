"""XML decoding and readable fields without importing Qt."""
from __future__ import annotations

import re

from gdt_tax.parser.xml_reader import localname

FIELD_LABELS = {
    'maTBao': 'Mã thông báo',
    'tenTBao': 'Tên thông báo',
    'soTBao': 'Số thông báo',
    'ngayTBao': 'Ngày thông báo',
    'trangThai': 'Trạng thái',
    'kyTinhThue': 'Kỳ tính thuế',
    'loaiToKhai': 'Loại tờ khai',
    'LyDo': 'Lý do',
    'maSoThue': 'MST',
    'mst': 'MST',
    'tenNNT': 'Người nộp thuế',
    'tenNguoiNopThue': 'Người nộp thuế',
    'coQuanThue': 'Cơ quan thuế',
    'tenCQT': 'Cơ quan thuế',
}
_ENCODING_RE = re.compile(rb'<\?xml[^>]*encoding=["\']([A-Za-z0-9._-]+)["\']', re.I)
_DTD_RE = re.compile(rb'<!\s*(DOCTYPE|ENTITY)\b', re.I)
_BOMS = (
    (b'\xef\xbb\xbf', 'utf-8-sig'),
    (b'\xff\xfe\x00\x00', 'utf-32'),
    (b'\x00\x00\xfe\xff', 'utf-32'),
    (b'\xff\xfe', 'utf-16'),
    (b'\xfe\xff', 'utf-16'),
)


def detect_encoding(data: bytes) -> str:
    """Đoán encoding để hiển thị; không ảnh hưởng byte gốc khi lưu."""
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            return encoding
    match = _ENCODING_RE.search(data[:200])
    if match:
        return match.group(1).decode('ascii', 'replace')
    return 'utf-8'


def decode_xml(data: bytes) -> tuple[str, str]:
    encoding = detect_encoding(data)
    try:
        return data.decode(encoding, errors='replace'), encoding
    except LookupError:
        return data.decode('utf-8', errors='replace'), 'utf-8'


def contains_dtd(data: bytes) -> bool:
    return bool(_DTD_RE.search(data[:8192]))


def readable_fields(root) -> dict[str, str]:
    """Trích các trường nghiệp vụ có thật; không suy đoán trường thiếu."""
    values: dict[str, str] = {}
    for element in root.iter():
        name = localname(element)
        label = FIELD_LABELS.get(name or '')
        if not label or label in values:
            continue
        text = ' '.join(part.strip() for part in element.itertext() if part.strip())
        if text:
            values[label] = text
    return values


