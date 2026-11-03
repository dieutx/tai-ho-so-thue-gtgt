"""Lưu ZIP và xuất metadata.

Thư mục tải về chứa:

* các file ``*.zip`` do cổng trả về
* ``danh_sach_ho_so.csv`` (UTF-8 BOM, mở tốt bằng Excel)
* ``danh_sach_ho_so.json``
* ``danh_sach_to_khai.xlsx`` (báo cáo tờ khai mở trực tiếp bằng Excel)
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
import zlib
from collections.abc import Iterable, Mapping
from io import BytesIO, StringIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from gdt_tax.spreadsheet_values import append_row, csv_value

from .archive_limits import (
    MAX_ARCHIVE_BYTES,
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_BYTES,
    MAX_MEMBERS,
    MAX_TOTAL_UNCOMPRESSED,
)
from .atomic import replace_with_retry
from .catalog import generation, serialized_catalog
from .classification import TAX_GROUPS
from .constants import METADATA_CSV, METADATA_JSON, METADATA_XLSX
from .contracts import DownloadArtifact
from .errors import StorageError
from .identity import key_from_row
from .integrity import (
    matches_evidence,
    read_bounded,
    safe_destination,
    source_reference,
    validate_tax_zip,
    write_evidence,
)
from .models import CaseRecord
from .naming import zip_filename

LOGGER_NAME = "gdt_tax.storage"


def required_document_kind(record: CaseRecord) -> str:
    """ZIP của hồ sơ thông báo (04/SS-HĐĐT...) chứa XML ``TBao``, không phải tờ khai."""
    if getattr(record, "loai_tai_lieu", "") == "NOTICE":
        return "notice"
    title = (getattr(record, "to_khai", "") or "").casefold()
    if "04/ss" in title or "thông báo" in title or "thong bao" in title:
        return "notice"
    return "declaration"

EXCEL_COLUMNS = (
    ("STT", None),
    ("Mã hồ sơ", "ma_ho_so"),
    ("Tên tờ khai", "to_khai"),
    ("Kỳ tính thuế", "ky_tinh_thue"),
    ("Loại tờ khai", "loai_to_khai"),
    ("Lần nộp bổ sung", "lan_bo_sung"),
    ("Lần nộp", "lan_nop"),
    ("Cơ quan thuế tiếp nhận", "noi_nop"),
    ("Ngày nộp", "ngay_nop"),
    ("Trạng thái", "trang_thai"),
    ("Hồ sơ đính kèm", "ho_so_dinh_kem"),
)


def valid_zip(data: bytes) -> bool:
    """Kiểm tra giới hạn tài nguyên trước khi giải nén để xác minh CRC của ZIP."""
    if len(data) > MAX_ARCHIVE_BYTES or not data.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS:
                return False
            total = 0
            for member in members:
                total += member.file_size
                if (
                    member.flag_bits & 1
                    or member.file_size > MAX_MEMBER_BYTES
                    or total > MAX_TOTAL_UNCOMPRESSED
                    or member.file_size / max(1, member.compress_size) > MAX_COMPRESSION_RATIO
                ):
                    return False
            return archive.testzip() is None
    except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError, zlib.error):
        return False


def decode_zip_bytes(response) -> bytes | None:
    """Lấy bytes ZIP từ phản hồi tải xuống.

    Cổng có lúc trả trực tiếp file nhị phân, có lúc trả JSON dạng
    ``{"content": "<base64>", "fileName": "..."}``.
    """
    if isinstance(response, DownloadArtifact):
        return response.data if response.media_kind == 'zip' and valid_zip(response.data) else None
    data = response.content
    if len(data) > (MAX_ARCHIVE_BYTES * 4 // 3 + 4096):
        return None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("content"):
        if not isinstance(payload["content"], str) or len(payload["content"]) > (MAX_ARCHIVE_BYTES + 2) // 3 * 4:
            return None
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
        #: Mã lỗi gần nhất để pipeline/UI báo đúng loại (ZIP hỏng vs sai loại hồ sơ).
        self.last_error = ""

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
                if candidate.stat().st_size > MAX_ARCHIVE_BYTES:
                    continue
                content = read_bounded(candidate, MAX_ARCHIVE_BYTES)
                if not validate_tax_zip(content, required_kind=required_document_kind(record)).ok or not matches_evidence(candidate, content, source_reference(record, "zip")):
                    continue
                record.tep_zip = candidate.name
                self.logger.info("Bỏ qua ZIP đã có: %s", candidate.name)
                return candidate
            except OSError:
                continue
        return None

    def save(self, record: CaseRecord, data: bytes) -> Path | None:
        """Ghi ZIP xuống đĩa sau khi kiểm tra tính toàn vẹn."""
        self.last_error = ""
        required_kind = required_document_kind(record)
        result = validate_tax_zip(data, required_kind=required_kind)
        if not result.ok:
            self.last_error = result.code
            self.logger.error(
                "Phản hồi không phải ZIP %s hợp lệ: %s (%s)",
                required_kind, record.ma_ho_so, result.code,
            )
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        path = safe_destination(self.path_for(record), data, source_reference(record, "zip"))
        _atomic_write(path, data)
        write_evidence(path, result, source_reference(record, "zip"))
        record.tep_zip = path.name
        self.logger.info("Đã lưu %s (%s bytes)", path.name, f"{len(data):,}")
        return path

    def save_from_response(self, record: CaseRecord, response) -> Path | None:
        self.last_error = ""
        data = decode_zip_bytes(response)
        if data is None:
            self.last_error = "ZIP_DECODE_FAILED"
            self.logger.error("Không giải mã được ZIP: %s", record.ma_ho_so)
            return None
        return self.save(record, data)


@serialized_catalog
def write_metadata(
    directory: str | Path,
    records: Mapping[str, CaseRecord] | Iterable[CaseRecord],
    *, materialize: bool = True,
) -> tuple[Path, Path] | None:
    """Gộp hồ sơ với JSON cũ, xuất CSV/JSON/Excel/nhóm; không ghi khi input rỗng."""
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
    merged = {key_from_row(row, "DECLARATION").serialize(): row for row in previous}
    for record in ordered:
        key = record.record_key
        row = {**merged.get(key, {}), **record.to_dict()}
        # Tra cứu/dry-run không được xoá tham chiếu của file đã tải lần trước.
        if not record.tep_zip and key in merged:
            row["tep_zip"] = merged[key].get("tep_zip", "")
        merged[key] = row
    rows = [merged[key] for key in sorted(merged)]
    _atomic_write(json_path, json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"))
    generation(json_path, [], ready=False)
    if not materialize:
        return directory / METADATA_CSV, json_path
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    csv_path = directory / METADATA_CSV
    with StringIO(newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: csv_value(value) for key, value in row.items()} for row in rows)
        csv_bytes = stream.getvalue().encode("utf-8-sig")
    groups: dict[str, list] = {group: [] for group in TAX_GROUPS}
    for row in rows:
        if row.get("tep_zip"):
            group = row.get("nhom_to_khai", "UNKNOWN")
            groups[group if group in groups else "UNKNOWN"].append(row)
    # JSON là danh mục chính. Mỗi file được thay thế nguyên tử; chưa có
    # transaction chung cho cả bốn danh mục (xem roadmap storage).
    _atomic_write(csv_path, csv_bytes)
    write_excel_report(directory / METADATA_XLSX, rows)
    grouped = {"schema_version": 1, "groups": groups}
    _atomic_write(directory / "phan_loai_ho_so.json",
                  json.dumps(grouped, ensure_ascii=False, indent=2).encode("utf-8"))
    generation(json_path, [csv_path, directory / METADATA_XLSX, directory / "phan_loai_ho_so.json"], ready=True)
    return csv_path, json_path


def write_excel_report(path: str | Path, rows: Iterable[Mapping[str, object]]) -> Path:
    """Xuất danh sách tờ khai dạng bảng Excel, an toàn với công thức từ dữ liệu ngoài."""
    from .attachments import attachment_sheet
    rows = list(rows)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Danh sách tờ khai"
    sheet.freeze_panes = "A2"
    append_row(sheet, [header for header, _ in EXCEL_COLUMNS])

    for index, row in enumerate(rows, start=1):
        values: list[object] = [index]
        for _, field in EXCEL_COLUMNS[1:]:
            value = row.get(field, "") if field else ""
            values.append(_excel_value(value))
        append_row(sheet, values)

    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    widths = (7, 28, 48, 18, 20, 18, 12, 40, 21, 32, 22)
    for column, width in zip(sheet.columns, widths, strict=True):
        sheet.column_dimensions[column[0].column_letter].width = width
    sheet.auto_filter.ref = sheet.dimensions
    if sheet.max_row > 1:
        table = Table(displayName="DanhSachToKhai", ref=sheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    attachment_sheet(workbook, rows)

    with BytesIO() as stream:
        workbook.save(stream)
        payload = stream.getvalue()
    workbook.close()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, payload)
    return target


def _excel_value(value: object) -> object:
    """Không để text do cổng trả về bị Excel diễn giải thành công thức."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _metadata_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("ma_ho_so"), str)
            or ("nguon" in row and not isinstance(row["nguon"], str)) for row in rows
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
        replace_with_retry(temporary, path)
    except OSError as error:
        raise StorageError(f"Không ghi được {path}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = [
    "ZipStore",
    "decode_zip_bytes",
    "valid_zip",
    "write_excel_report",
    "write_metadata",
]
