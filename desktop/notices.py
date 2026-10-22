"""Liệt kê thông báo đính kèm và đọc trạng thái từ XML của cơ quan thuế.

Chỉ đọc tệp đã tải trong ``<nơi lưu>/thong-bao-dinh-kem/<mã hồ sơ>/``; không
gọi mạng, không đổi tên và không sửa tệp. Dùng để hiển thị thông báo của cơ
quan thuế theo từng tờ khai và cảnh báo tờ khai không được chấp nhận.
"""
from __future__ import annotations

import hashlib
import json
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
REFERENCE_LABELS = {'VERIFIED': 'Đã đối chiếu tham chiếu và checksum',
                    'LEGACY_UNVERIFIED': 'Tệp cũ; chưa xác minh tham chiếu',
                    'NOT_CHECKED': 'Chưa đối chiếu checksum; tệp lớn',
                    'INVALID': 'Tệp hoặc tham chiếu không khớp; cần kiểm tra'}
KIND_LABELS = {"tiep-nhan": "Tiếp nhận", "chap-nhan": "Chấp nhận",
               "khong-chap-nhan": "Không chấp nhận", "khac": "Thông báo"}
_FIELDS = {"maTBao": "ma_thong_bao", "tenTBao": "ten_thong_bao", "soTBao": "so_thong_bao",
           "ngayTBao": "ngay_thong_bao", "trangThai": "trang_thai", "LyDo": "ly_do",
           "kyTinhThue": "ky_tinh_thue", "loaiToKhai": "loai_to_khai"}
_REJECT_MARKERS = ("khong chap nhan", "khong duoc chap nhan", "tu choi")
_REJECT_STATUS = {"n", "no", "0", "false", "khong", "khong chap nhan"}
_ACCEPT_STATUS = {"y", "chap nhan"}


def _fold(value: str) -> str:
    text = str(value or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def notice_directory(output: str | Path, case_id: str) -> Path:
    """Thư mục thông báo đính kèm của một hồ sơ, cùng quy ước với ``NoticeStore``."""
    return Path(output) / NOTICE_DIRECTORY / safe_filename_part(case_id, 60)


def _read_fields(data: bytes) -> dict[str, str]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {}
    if root.tag.rsplit('}', 1)[-1] != 'TBaoThueDTu':
        return {}
    fields: dict[str, str] = {}
    for element in root.iter():
        key = _FIELDS.get(element.tag.rsplit("}", 1)[-1])
        if not key or key in fields:
            continue
        value = ' '.join(part.strip() for part in element.itertext() if part.strip()) if key == 'ly_do' else (element.text or '').strip()
        if value:
            fields[key] = value
    return fields


def _kind(name: str, fields: dict[str, str]) -> str:
    text = re.sub(r"[^a-z0-9/]+", " ", _fold(fields.get('ten_thong_bao') or name))
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
    if not fields:
        return ''
    if kind == "khong-chap-nhan":
        return REJECTED
    if kind == "tiep-nhan":
        return RECEIVED
    # Văn bản legacy gộp "Chấp nhận/Không chấp nhận": phải đọc nội dung.
    if (fields.get("ly_do") or "").strip():
        return REJECTED
    if _fold(fields.get("trang_thai", "")) in _REJECT_STATUS:
        return REJECTED
    status = _fold(fields.get('trang_thai', ''))
    if status and status not in _ACCEPT_STATUS:
        return ''
    if kind == "chap-nhan" or status in _ACCEPT_STATUS:
        return ACCEPTED
    return ""


def read_notices(output: str | Path, case_id: str, *, parent_key: str = '') -> list[dict]:
    """Liệt kê XML/PDF/ZIP đã tải; chỉ suy ra trạng thái từ XML đọc được.

    ``parent_key`` đối chiếu ownership khi core cung cấp định danh đầy đủ.
    Tệp cũ thiếu evidence vẫn mở được nhưng không kết luận trạng thái cho
    hồ sơ có ownership. Không ghi lại XML hoặc sidecar trong quá trình đọc.
    """
    root = Path(output).resolve()
    directory = notice_directory(output, case_id)
    if not case_id or not directory.is_dir() or not directory.resolve().is_relative_to(root):
        return []
    notices: list[dict] = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {'.xml', '.pdf', '.zip'}:
            continue
        try:
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            size = path.stat().st_size
            data = b''
            if size <= MAX_PARSE_BYTES:
                with path.open('rb') as stream:
                    data = stream.read(MAX_PARSE_BYTES + 1)
                if len(data) > MAX_PARSE_BYTES:
                    data = b''
        except OSError:
            continue
        evidence = path.with_name(path.name + '.integrity.json')
        reference_status = 'LEGACY_UNVERIFIED'
        reference_key = ''
        digest = hashlib.sha256(data).hexdigest() if data else ''
        if evidence.exists():
            try:
                if evidence.is_symlink() or evidence.stat().st_size > 32 * 1024:
                    raise ValueError('Unsafe evidence')
                info = json.loads(evidence.read_text(encoding='utf-8'))
                source = info['source']
                if source.get('parent_remote_id') != case_id or parent_key and source.get('parent_record_key') != parent_key:
                    continue
                reference_key = source.get('record_key', '')
                if size > MAX_PARSE_BYTES:
                    reference_status = 'NOT_CHECKED'
                elif digest and info.get('sha256') == digest and info.get('size') == size and info.get('status') == 'OK':
                    reference_status = 'VERIFIED'
                else:
                    reference_status = 'INVALID'
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                reference_status = 'INVALID'
        fields = _read_fields(data) if data and path.suffix.lower() == '.xml' and reference_status != 'INVALID' else {}
        kind = _kind(path.name, fields)
        read_status = 'PARSED' if fields else 'UNREADABLE'
        if path.suffix.lower() != '.xml':
            read_status = 'UNSUPPORTED'
        elif size > MAX_PARSE_BYTES:
            read_status = 'TOO_LARGE'
        notices.append({
            "path": str(path),
            "name": path.name,
            "kind": kind,
            "kind_label": KIND_LABELS[kind],
            "state": _state(kind, fields) if not parent_key or reference_status == 'VERIFIED' else '',
            "parent_key": parent_key,
            "reference_key": reference_key,
            "relative_path": path.relative_to(output).as_posix(),
            "reference_status": reference_status,
            "sha256": digest,
            "size": size,
            "read_status": read_status,
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
    if not notices:
        return ""
    label = STATE_LABELS.get(state, 'Chưa xác định')
    return label if len(notices) <= 1 else f"{label} ({len(notices)})"


def is_rejected(row: dict) -> bool:
    return row.get("_notice_state") == REJECTED


__all__ = [
    "ACCEPTED",
    "KIND_LABELS",
    "RECEIVED",
    "REJECTED",
    "STATE_LABELS",
    "REFERENCE_LABELS",
    "is_rejected",
    "notice_directory",
    "notice_state",
    "notice_summary",
    "read_notices",
]
