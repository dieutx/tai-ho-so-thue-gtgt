"""Lưu file XML giấy nộp tiền và xuất danh mục.

Thư mục tải về chứa:

* các file ``*.xml`` — mỗi giấy nộp tiền một file ``<số GNT>__<ctuId>.xml``
* ``danh_sach_giay_nop_tien.csv`` (UTF-8 BOM, mở tốt bằng Excel)
* ``danh_sach_giay_nop_tien.json``
* ``danh_sach_giay_nop_tien.xlsx`` (bảng tổng hợp GNT)

File XML đã tải hợp lệ sẽ được bỏ qua ở lần chạy sau, nên có thể chạy tiếp khi bị
gián đoạn.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import tempfile
from collections.abc import Iterable, Mapping
from io import BytesIO, StringIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from gdt_tax.spreadsheet_values import append_row, csv_value

from ..atomic import replace_with_retry
from ..constants import GNT_METADATA_CSV, GNT_METADATA_JSON, GNT_METADATA_XLSX
from ..errors import StorageError
from ..integrity import (
    candidate_paths,
    matches_evidence,
    read_bounded,
    safe_destination,
    source_reference,
    validate_xml,
    write_evidence,
)
from ..xml_policy import MAX_XML_BYTES
from .models import GiayNopTien
from .naming import gnt_xml_filename
from .portal import is_gnt_xml

LOGGER_NAME = "gdt_tax.gnt.storage"

EXCEL_COLUMNS = (
    ("STT", None),
    ("Số tham chiếu/Mã giao dịch", "so_tham_chieu"),
    ("Mã giao dịch DS chi tiết", "ma_giao_dich_chi_tiet"),
    ("Lần nộp", "lan_nop"),
    ("Số giấy nộp tiền", "so_gnt"),
    ("Số tiền", "so_tien"),
    ("Loại tiền", "loai_tien"),
    ("Trạng thái", "trang_thai"),
    ("Số chứng từ", "so_chung_tu"),
    ("Ngày lập GNT", "ngay_lap"),
    ("Ngày gửi GNT", "ngay_gui"),
    ("Ngày nộp thuế", "ngay_nop"),
    ("DS chi tiết TNCN", "co_ds_chi_tiet_tncn"),
    ("DS chi tiết TMĐT", "co_ds_chi_tiet_tmdt"),
    ("Ngày nộp DS chi tiết", "ngay_nop_ds_chi_tiet"),
    ("Hình thức nộp", "hinh_thuc_nop"),
    ("Ngân hàng", "ngan_hang"),
    ("Tài khoản ngân hàng", "tai_khoan"),
    ("File XML", "tep_xml"),
    ("Thông báo", "thong_bao"),
)

_EXCEL_WIDTHS = (6, 26, 20, 10, 40, 16, 10, 22, 16, 20, 20, 20, 14, 14, 20, 28, 34, 22, 44, 24)


class GntStore:
    """Quản lý file XML giấy nộp tiền: kiểm tra trùng, lưu file."""

    def __init__(self, directory: str | Path, logger: logging.Logger | None = None) -> None:
        self.directory = Path(directory)
        self.logger = logger or logging.getLogger(LOGGER_NAME)

    def path_for(self, record: GiayNopTien) -> Path:
        return self.directory / gnt_xml_filename(record)

    def find_existing(self, record: GiayNopTien) -> Path | None:
        """Trả về file XML đã có nếu hợp lệ (dùng để resume)."""
        for path in candidate_paths(self.path_for(record), record.tep_xml):
            if not path.is_file():
                continue
            try:
                content = read_bounded(path, MAX_XML_BYTES)
                if not is_gnt_xml(content) or not matches_evidence(path, content, source_reference(record, "gnt")):
                    continue
            except OSError:
                continue
            record.tep_xml = path.name
            self.logger.info("Bỏ qua GNT đã có: %s", path.name)
            return path
        return None

    def save(self, record: GiayNopTien, data: bytes) -> Path | None:
        """Ghi file XML sau khi kiểm tra nội dung."""
        if not is_gnt_xml(data):
            self.logger.error("Phản hồi không phải XML GNT hợp lệ: %s", record.ctu_id)
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        path = safe_destination(self.path_for(record), data, source_reference(record, "gnt"))
        _atomic_write(path, data)
        write_evidence(path, validate_xml(data, "gnt"), source_reference(record, "gnt"))
        record.tep_xml = path.name
        self.logger.info("Đã lưu %s (%s bytes)", path.name, f"{len(data):,}")
        return path


def write_gnt_metadata(
    directory: str | Path,
    records: Mapping[str, GiayNopTien] | Iterable[GiayNopTien],
) -> tuple[Path, Path] | None:
    """Gộp GNT với JSON cũ, xuất CSV/JSON/Excel; không ghi khi input rỗng."""
    if isinstance(records, Mapping):
        ordered = [records[key] for key in sorted(records)]
    else:
        ordered = sorted(records, key=lambda item: item.ctu_id)
    if not ordered:
        return None

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / GNT_METADATA_JSON
    previous = _metadata_rows(json_path)
    merged = {row["ctu_id"]: row for row in previous}
    for record in ordered:
        key = record.ctu_id
        row = {**merged.get(key, {}), **record.to_dict()}
        # Tra cứu/dry-run không được xoá tham chiếu file đã tải lần trước.
        if not record.tep_xml and key in merged:
            row["tep_xml"] = merged[key].get("tep_xml", "")
        merged[key] = row
    rows = [merged[key] for key in sorted(merged)]
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    csv_path = directory / GNT_METADATA_CSV
    with StringIO(newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: csv_value(value) for key, value in row.items()} for row in rows)
        csv_bytes = stream.getvalue().encode("utf-8-sig")
    _atomic_write(json_path, json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"))
    _atomic_write(csv_path, csv_bytes)
    write_gnt_excel_report(directory / GNT_METADATA_XLSX, rows)
    return csv_path, json_path


def write_gnt_excel_report(path: str | Path, rows: Iterable[Mapping[str, object]]) -> Path:
    """Xuất bảng tổng hợp giấy nộp tiền, an toàn với công thức từ dữ liệu ngoài."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Danh sách giấy nộp tiền"
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

    for column, width in zip(sheet.columns, _EXCEL_WIDTHS, strict=True):
        sheet.column_dimensions[column[0].column_letter].width = width
    sheet.auto_filter.ref = sheet.dimensions
    if sheet.max_row > 1:
        table = Table(displayName="DanhSachGiayNopTien", ref=sheet.dimensions)
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
            not isinstance(row, dict) or not isinstance(row.get("ctu_id"), str) or not row["ctu_id"]
            for row in rows
        ):
            raise ValueError("metadata GNT phải là danh sách có ctu_id")
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
    "EXCEL_COLUMNS",
    "GntStore",
    "write_gnt_excel_report",
    "write_gnt_metadata",
]
