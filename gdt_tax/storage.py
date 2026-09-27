"""Lưu ZIP và xuất metadata.

Thư mục tải về chứa:

* các file ``*.zip`` do cổng trả về
* ``danh_sach_ho_so.csv`` (UTF-8 BOM, mở tốt bằng Excel)
* ``danh_sach_ho_so.json``
* ``phan_loai_ho_so.json`` (danh mục nhóm cho hồ sơ có file đã tải)

ZIP đã tải hợp lệ sẽ được bỏ qua ở lần chạy sau, nên có thể chạy tiếp khi bị gián đoạn.
"""

from __future__ import annotations

import base64
import csv
import json
import logging
import os
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from io import BytesIO, StringIO
from pathlib import Path

from .classification import TAX_GROUPS
from .constants import METADATA_CSV, METADATA_JSON
from .errors import StorageError
from .models import CaseRecord
from .naming import zip_filename

LOGGER_NAME = "gdt_tax.storage"


def valid_zip(data: bytes) -> bool:
    """Kiểm tra dữ liệu có phải ZIP nguyên vẹn (không chỉ có chữ ký ``PK``)."""
    if not data.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            return archive.testzip() is None
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError):
        return False


def decode_zip_bytes(response) -> bytes | None:
    """Lấy bytes ZIP từ phản hồi tải xuống.

    Cổng có lúc trả trực tiếp file nhị phân, có lúc trả JSON dạng
    ``{"content": "<base64>", "fileName": "..."}``.
    """
    data = response.content
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("content"):
        try:
            data = base64.b64decode(payload["content"], validate=True)
        except (ValueError, TypeError):
            pass
    return data if valid_zip(data) else None


class ZipStore:
    """Quản lý thư mục ZIP: kiểm tra trùng, lưu file, ghi metadata."""

    def __init__(self, directory: str | Path, logger: logging.Logger | None = None) -> None:
        self.directory = Path(directory)
        self.logger = logger or logging.getLogger(LOGGER_NAME)

    def path_for(self, record: CaseRecord) -> Path:
        return self.directory / zip_filename(record)

    def find_existing(self, record: CaseRecord) -> Path | None:
        """Trả về file ZIP đã có nếu hợp lệ; đổi tên về đúng quy ước khi cần."""
        self.directory.mkdir(parents=True, exist_ok=True)
        preferred = self.path_for(record)
        # Mã phải ở đầu tên và có ranh giới; 123 không được khớp 9123/1234.
        # Tên cũ dạng <id>-ten.zip vẫn được hỗ trợ, không dùng glob từ mã.
        candidates = [preferred, *sorted(
            path for path in self.directory.glob("*.zip")
            if path.stem == record.ma_ho_so
            or path.name.startswith(f"{record.ma_ho_so}__")
            or path.name.startswith(f"{record.ma_ho_so}-")
        )]
        checked: set[Path] = set()
        for candidate in candidates:
            if candidate in checked or not candidate.is_file():
                continue
            checked.add(candidate)
            try:
                if not valid_zip(candidate.read_bytes()):
                    continue
                if candidate != preferred and not preferred.exists():
                    candidate.rename(preferred)
                    candidate = preferred
                record.tep_zip = candidate.name
                self.logger.info("Bỏ qua ZIP đã có: %s", candidate.name)
                return candidate
            except OSError:
                continue
        return None

    def save(self, record: CaseRecord, data: bytes) -> Path | None:
        """Ghi ZIP xuống đĩa sau khi kiểm tra tính toàn vẹn."""
        if not valid_zip(data):
            self.logger.error("Phản hồi không phải ZIP hợp lệ: %s", record.ma_ho_so)
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(record)
        _atomic_write(path, data)
        record.tep_zip = path.name
        self.logger.info("Đã lưu %s (%s bytes)", path.name, f"{len(data):,}")
        return path

    def save_from_response(self, record: CaseRecord, response) -> Path | None:
        data = decode_zip_bytes(response)
        if data is None:
            self.logger.error("Không giải mã được ZIP: %s", record.ma_ho_so)
            return None
        return self.save(record, data)


def write_metadata(
    directory: str | Path,
    records: Mapping[str, CaseRecord] | Iterable[CaseRecord],
) -> tuple[Path, Path] | None:
    """Gộp hồ sơ với JSON cũ, xuất CSV/JSON/nhóm; không ghi khi input rỗng."""
    if isinstance(records, Mapping):
        ordered = [records[key] for key in sorted(records)]
    else:
        ordered = sorted(records, key=lambda item: item.ma_ho_so)
    if not ordered:
        return None

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / METADATA_JSON
    previous = _metadata_rows(json_path)
    merged = {(row["nguon"], row["ma_ho_so"]): row for row in previous}
    for record in ordered:
        key = (record.nguon, record.ma_ho_so)
        row = {**merged.get(key, {}), **record.to_dict()}
        # Tra cứu/dry-run không được xoá tham chiếu của file đã tải lần trước.
        if not record.tep_zip and key in merged:
            row["tep_zip"] = merged[key].get("tep_zip", "")
        merged[key] = row
    rows = [merged[key] for key in sorted(merged)]
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    csv_path = directory / METADATA_CSV
    with StringIO(newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = stream.getvalue().encode("utf-8-sig")
    groups: dict[str, list] = {group: [] for group in TAX_GROUPS}
    for row in rows:
        if row.get("tep_zip"):
            group = row.get("nhom_to_khai", "UNKNOWN")
            groups[group if group in groups else "UNKNOWN"].append(row)
    # JSON là danh mục chính. Mỗi file được thay thế nguyên tử; chưa có
    # transaction chung cho cả ba danh mục (xem roadmap storage).
    _atomic_write(json_path, json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"))
    _atomic_write(csv_path, csv_bytes)
    grouped = {"schema_version": 1, "groups": groups}
    _atomic_write(directory / "phan_loai_ho_so.json",
                  json.dumps(grouped, ensure_ascii=False, indent=2).encode("utf-8"))
    return csv_path, json_path


def _metadata_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("ma_ho_so"), str)
            or not isinstance(row.get("nguon"), str) for row in rows
        ):
            raise ValueError("metadata phải là danh sách hồ sơ có ma_ho_so và nguon")
        return rows
    except (OSError, ValueError) as error:
        raise StorageError(f"Không đọc được {path}; giữ nguyên metadata cũ: {error}") from error


def _atomic_write(path: Path, data: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as stream:
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


__all__ = [
    "ZipStore",
    "decode_zip_bytes",
    "valid_zip",
    "write_metadata",
]
