"""Đọc thông báo XML đính kèm hồ sơ (tiếp nhận / chấp nhận / không chấp nhận).

Chỉ đọc tệp đã tải trong ``<nơi lưu>/thong-bao-dinh-kem/<mã hồ sơ>/``; không
gọi mạng, không đổi tên và không sửa tệp. Dùng để hiển thị thông báo của cơ
quan thuế theo từng tờ khai và cảnh báo tờ khai không được chấp nhận.
"""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from gdt_tax.dvc_notices import NOTICE_DIRECTORY
from gdt_tax.naming import safe_filename_part

#: Bỏ qua parse với văn bản lớn hơn ngưỡng; tệp vẫn được liệt kê để mở.
MAX_PARSE_BYTES = 4 * 1024 * 1024
ACCEPTED = "accepted"
REJECTED = "rejected"
RECEIVED = "received"
STATE_LABELS = {ACCEPTED: "Chấp nhận", REJECTED: "Không chấp nhận", RECEIVED: "Tiếp nhận"}
KIND_LABELS = {"tiep-nhan": "Tiếp nhận", "chap-nhan": "Chấp nhận",
               "khong-chap-nhan": "Không chấp nhận", "khac": "Thông báo"}
_FIELDS = {"maTBao": "ma_thong_bao", "tenTBao": "ten_thong_bao", "soTBao": "so_thong_bao",
           "ngayTBao": "ngay_thong_bao", "trangThai": "trang_thai", "LyDo": "ly_do",
           "kyTinhThue": "ky_tinh_thue", "loaiToKhai": "loai_to_khai"}
_REJECT_MARKERS = ("khong chap nhan", "khong duoc chap nhan", "tu choi")
_REJECT_STATUS = {"n", "no", "0", "false", "khong", "khong chap nhan"}


def _fold(value: str) -> str:
    text = str(value or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def notice_directory(output: str | Path, case_id: str) -> Path:
    """Thư mục thông báo đính kèm của một hồ sơ, cùng quy ước với ``NoticeStore``."""
    return Path(output) / NOTICE_DIRECTORY / safe_filename_part(case_id, 60)


def _read_fields(path: Path) -> dict[str, str]:
    try:
        if path.stat().st_size > MAX_PARSE_BYTES:
            return {}
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}
    fields: dict[str, str] = {}
    for element in root.iter():
        key = _FIELDS.get(element.tag.rsplit("}", 1)[-1])
        if not key or key in fields:
            continue
        value = (element.text or "").strip()
        if value:
            fields[key] = value
    return fields


def _kind(name: str, fields: dict[str, str]) -> str:
    text = re.sub(r"[^a-z0-9/]+", " ", _fold(f"{name} {fields.get('ten_thong_bao', '')}"))
    # Văn bản legacy gộp cả hai kết quả trong một tiêu đề; phải đọc nội dung.
    if "chap nhan/khong chap nhan" in text or "chap nhan khong chap nhan" in text:
        return "khac"
    if any(marker in text for marker in _REJECT_MARKERS):
        return "khong-chap-nhan"
    if "tiep nhan" in text:
        return "tiep-nhan"
    if "chap nhan" in text or "xac nhan" in text:
        return "chap-nhan"
    return "khac"


def _state(kind: str, fields: dict[str, str]) -> str:
    if kind == "khong-chap-nhan":
        return REJECTED
    if kind == "tiep-nhan":
        return RECEIVED
    # Văn bản legacy gộp "Chấp nhận/Không chấp nhận": phải đọc nội dung.
    if (fields.get("ly_do") or "").strip():
        return REJECTED
    if _fold(fields.get("trang_thai", "")) in _REJECT_STATUS:
        return REJECTED
    if kind == "chap-nhan" or fields.get("trang_thai"):
        return ACCEPTED
    return ""


def read_notices(output: str | Path, case_id: str) -> list[dict]:
    """Liệt kê thông báo XML đã tải của hồ sơ, kèm trạng thái đọc được."""
    directory = notice_directory(output, case_id)
    if not directory.is_dir():
        return []
    notices: list[dict] = []
    for path in sorted(directory.glob("*.xml")):
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        fields = _read_fields(path)
        kind = _kind(path.name, fields)
        notices.append({
            "path": str(path),
            "name": path.name,
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "state": _state(kind, fields),
            "ma_thong_bao": fields.get("ma_thong_bao", ""),
            "so_thong_bao": fields.get("so_thong_bao", ""),
            "ten_thong_bao": fields.get("ten_thong_bao", ""),
            "ngay_thong_bao": fields.get("ngay_thong_bao", ""),
            "ly_do": fields.get("ly_do", ""),
        })
    order = {"tiep-nhan": 0, "khong-chap-nhan": 1, "chap-nhan": 1, "khac": 2}
    notices.sort(key=lambda item: (order.get(item["kind"], 3), item["name"]))
    return notices


def notice_state(notices: list[dict]) -> str:
    """Trạng thái tổng hợp của hồ sơ; từ chối thắng mọi trạng thái khác."""
    states = {item.get("state") for item in notices}
    if REJECTED in states:
        return REJECTED
    if ACCEPTED in states:
        return ACCEPTED
    if RECEIVED in states:
        return RECEIVED
    return ""


def notice_summary(notices: list[dict]) -> str:
    """Nhãn ngắn cho cột Thông báo; rỗng khi hồ sơ chưa có thông báo trên máy."""
    state = notice_state(notices)
    if not state:
        return ""
    label = STATE_LABELS[state]
    return label if len(notices) <= 1 else f"{label} ({len(notices)})"


def is_rejected(row: dict) -> bool:
    return row.get("_notice_state") == REJECTED


__all__ = [
    "ACCEPTED",
    "KIND_LABELS",
    "RECEIVED",
    "REJECTED",
    "STATE_LABELS",
    "is_rejected",
    "notice_directory",
    "notice_state",
    "notice_summary",
    "read_notices",
]
