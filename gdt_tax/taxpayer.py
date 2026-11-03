"""Nhận diện và lưu tên người nộp thuế theo mã số thuế.

Sau khi đăng nhập, trang hồ sơ ``/tthc/tchs`` in tên người nộp thuế cạnh mã số
thuế (doanh nghiệp) hoặc số định danh (cá nhân). Tên này được lưu vào
``nguoi_nop_thue.json`` trong thư mục tải về, khoá theo mã số thuế, để tra cứu
lại mà không phải đăng nhập lần nữa.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup

from .constants import TAXPAYER_REGISTRY_JSON
from .errors import StorageError

REGISTRY_SCHEMA_VERSION = 1
_IDENTIFIER_RE = re.compile(r"(?:Số định danh|Mã số thuế)\s*[:：]\s*([0-9A-Za-z_-]+)")
#: Tài khoản doanh nghiệp thường có dạng ``<MST>-QL``; tài khoản cá nhân là số
#: định danh thuần, dùng làm phương án dự phòng khi trang không in nhãn.
_USERNAME_RE = re.compile(r"^([0-9]{10,14})(?:-|$)")


@dataclass(frozen=True)
class Taxpayer:
    """Tên và mã số thuế đọc được từ trang hồ sơ sau khi đăng nhập."""

    mst: str
    ten_nguoi_nop_thue: str


def parse_taxpayer(html: str, username: str = "") -> Taxpayer | None:
    """Đọc tên + MST từ HTML trang hồ sơ; ``None`` nếu thiếu một trong hai."""
    soup = BeautifulSoup(html, "lxml")
    # Script của cổng có thể chứa mã số thuế của đơn vị khác (chatbox), không lấy.
    for tag in soup(["script", "style"]):
        tag.decompose()
    name_tag = soup.select_one("span.ten_dn")
    name = name_tag.get_text(" ", strip=True) if name_tag else ""
    text = soup.get_text(" ", strip=True)
    match = _IDENTIFIER_RE.search(text)
    mst = match.group(1) if match else ""
    if not mst:
        fallback = _USERNAME_RE.match(username.strip())
        mst = fallback.group(1) if fallback else ""
    if not name or not mst:
        return None
    return Taxpayer(mst=mst, ten_nguoi_nop_thue=name)


def save_taxpayer(
    directory: str | Path, taxpayer: Taxpayer, *, now: datetime | None = None
) -> Path:
    """Gộp tên người nộp thuế vào danh mục theo MST; không ghi đè dữ liệu hỏng."""
    path = Path(directory) / TAXPAYER_REGISTRY_JSON
    entries = _read_registry(path)
    entries[taxpayer.mst] = {
        **entries.get(taxpayer.mst, {}),
        "ten_nguoi_nop_thue": taxpayer.ten_nguoi_nop_thue,
        "cap_nhat": (now or datetime.now()).isoformat(timespec="seconds"),
    }
    payload = {"schema_version": REGISTRY_SCHEMA_VERSION, "nguoi_nop_thue": entries}
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    return path


def _read_registry(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StorageError(f"Không đọc được {path}; giữ nguyên danh mục cũ: {error}") from error
    entries = payload.get("nguoi_nop_thue") if isinstance(payload, dict) else None
    if not isinstance(entries, dict):
        raise StorageError(f"Không đọc được {path}; giữ nguyên danh mục cũ")
    return {str(key): dict(value) for key, value in entries.items() if isinstance(value, dict)}


def _atomic_write(path: Path, data: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise StorageError(f"Không ghi được {path}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = ["Taxpayer", "parse_taxpayer", "save_taxpayer"]
