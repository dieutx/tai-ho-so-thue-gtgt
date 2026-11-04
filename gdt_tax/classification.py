"""Phân nhóm từ metadata; không suy đoán schema hay chỉ tiêu trong XML.

Giữ file gốc trong cùng thư mục, xuất danh mục nhóm trỏ tới tep_zip. Một ZIP
có thể chứa nhiều tài liệu; nhóm hồ sơ chỉ là gợi ý cho bước inventory sau này.
"""

from __future__ import annotations

import re
import unicodedata

from .models import CaseRecord

CLASSIFICATION_VERSION = "metadata-keyword-v3"
TAX_GROUPS = ("GTGT", "TNCN", "TNDN", "OTHER", "UNKNOWN")
_GROUP_TERMS = {
    "GTGT": ("gtgt", "gia tri gia tang"),
    "TNCN": ("tncn", "thu nhap ca nhan"),
    "TNDN": ("tndn", "thu nhap doanh nghiep"),
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower().replace("đ", "d"))
    return re.sub(r"[^a-z0-9]+", " ", "".join(
        char for char in value if not unicodedata.combining(char)
    )).strip()


def is_rental_declaration(title: str) -> bool:
    """01/BĐS has a dual-purpose title but downloads a HSoThueDTu declaration."""
    normalized = _normalize(title)
    return normalized.startswith('01 bds ') and 'to khai thue' in normalized


def is_invoice_notice_declaration(title: str) -> bool:
    """TB01/AC, TB03/AC say "thông báo" but the portal returns HSoThueDTu.

    Their titles contain "thông báo" (phát hành/hủy hóa đơn), so a title-only
    rule classifies them as notices. The downloaded file is a declaration
    (``maTKhai`` 106/107), so the notice schema check would reject it.
    """
    return bool(re.match(r"tb\d+ ac\b", _normalize(title)))


def classify_record(record: CaseRecord) -> CaseRecord:
    """Phân loại có lý do; tín hiệu mâu thuẫn được giữ UNKNOWN để kiểm tra."""
    title = _normalize(record.to_khai)
    text = f" {title} {_normalize(record.ten_tthc)} "
    matches = {
        group: term for group, terms in _GROUP_TERMS.items()
        for term in terms if f" {term} " in text
    }
    record.quy_tac_phan_loai = CLASSIFICATION_VERSION
    record.nhom_to_khai = "UNKNOWN"
    record.loai_tai_lieu = "UNKNOWN"
    if is_rental_declaration(record.to_khai) or is_invoice_notice_declaration(record.to_khai):
        record.loai_tai_lieu = "DECLARATION"
    elif "thong bao" in title:
        record.loai_tai_lieu = "NOTICE"
    elif "phu luc" in title and "to khai" not in title:
        record.loai_tai_lieu = "APPENDIX"
    elif "to khai" in title or "quyet toan" in title:
        record.loai_tai_lieu = "DECLARATION"
    if len(matches) == 1:
        record.nhom_to_khai = next(iter(matches))
        record.ly_do_phan_loai = f"metadata: {next(iter(matches.values()))}"
    elif len(matches) > 1:
        record.ly_do_phan_loai = f"metadata mâu thuẫn: {', '.join(sorted(matches))}"
    else:
        if record.loai_tai_lieu != "UNKNOWN":
            record.nhom_to_khai = "OTHER"
        record.ly_do_phan_loai = "metadata chưa có từ khóa xác định nhóm thuế"
    return record


__all__ = ["CLASSIFICATION_VERSION", "TAX_GROUPS", "classify_record",
           "is_invoice_notice_declaration", "is_rental_declaration"]
