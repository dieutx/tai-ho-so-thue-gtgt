"""Lưu file PDF thông báo và xuất danh mục.

Thư mục chứa:

* các file ``*.pdf`` — mỗi thông báo một file ``<số thông báo>__<messageId>.pdf``
* ``danh_sach_thong_bao.csv`` (UTF-8 BOM), ``danh_sach_thong_bao.json``
* ``danh_sach_thong_bao.xlsx`` (bảng tổng hợp thông báo)

File PDF đã tải hợp lệ được bỏ qua ở lần chạy sau.
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

from ..archive_limits import MAX_MEMBER_BYTES
from ..atomic import replace_with_retry
from ..catalog import generation, serialized_catalog
from ..constants import TB_METADATA_CSV, TB_METADATA_JSON, TB_METADATA_XLSX
from ..errors import StorageError
from ..identity import key_from_row
from ..integrity import (
    candidate_paths,
    matches_evidence,
    read_bounded,
    safe_destination,
    source_reference,
    validate_pdf,
    validate_xml,
    write_evidence,
)
from .models import ThongBao
from .naming import tb_pdf_filename
from .portal import is_tb_document

LOGGER_NAME = "gdt_tax.tb.storage"

EXCEL_COLUMNS = (
    ("STT", None),
    ("Mã thông báo", "ma_thong_bao"),
    ("Tên thông báo", "ten_thong_bao"),
    ("Số thông báo", "so_thong_bao"),
    ("Ngày gửi thông báo", "ngay_gui"),
    ("Cơ quan gửi", "co_quan_gui"),
    ("Trạng thái", "trang_thai"),
    ("Văn bản giải trình điện tử", "co_van_ban_giai_trinh"),
    ("Phản hồi kết quả rà soát", "co_phan_hoi_ra_soat"),
    ("File PDF", "tep_pdf"),
)

_EXCEL_WIDTHS = (6, 14, 46, 26, 22, 40, 12, 22, 22, 46)


class TbStore:
    """Quản lý file PDF thông báo: kiểm tra trùng, lưu file."""

    def __init__(self, directory: str | Path, logger: logging.Logger | None = None) -> None:
        self.directory = Path(directory)
        self.logger = logger or logging.getLogger(LOGGER_NAME)

    def path_for(self, record: ThongBao) -> Path:
        return self.directory / tb_pdf_filename(record)

    def find_existing(self, record: ThongBao) -> Path | None:
        """Trả về file PDF đã có nếu hợp lệ (dùng để resume)."""
        paths = candidate_paths(self.path_for(record), record.tep_pdf)
        paths.extend(candidate_paths(self.path_for(record).with_suffix(".xml"), record.tep_pdf))
        for path in dict.fromkeys(paths):
            if not path.is_file():
                continue
            try:
                content = read_bounded(path, MAX_MEMBER_BYTES)
                if not is_tb_document(content) or not matches_evidence(path, content, source_reference(record, "pdf")):
                    continue
            except OSError:
                continue
            record.tep_pdf = path.name
            self.logger.info("Bỏ qua thông báo đã có: %s", path.name)
            return path
        return None

    def save(self, record: ThongBao, data: bytes) -> Path | None:
        """Ghi file PDF hoặc XML thông báo sau khi kiểm tra nội dung."""
        pdf_result = validate_pdf(data)
        xml_result = None if pdf_result.ok else validate_xml(data, "notice")
        if pdf_result.ok:
            result = pdf_result
        elif xml_result is not None and xml_result.ok:
            result = xml_result
        else:
            self.logger.error("Phản hồi không phải PDF/XML thông báo hợp lệ: %s",
                              record.message_id)
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        preferred = self.path_for(record) if pdf_result.ok else self.path_for(record).with_suffix(".xml")
        path = safe_destination(preferred, data, source_reference(record, "pdf"))
        _atomic_write(path, data)
        write_evidence(path, result, source_reference(record, "pdf"))
        record.tep_pdf = path.name
        self.logger.info("Đã lưu %s (%s bytes)", path.name, f"{len(data):,}")
        return path


@serialized_catalog
def write_tb_metadata(
    directory: str | Path,
    records: Mapping[str, ThongBao] | Iterable[ThongBao],
    *, materialize: bool = True,
) -> tuple[Path, Path] | None:
    """Gộp thông báo với JSON cũ, xuất CSV/JSON/Excel; không ghi khi input rỗng."""
    if isinstance(records, Mapping):
        ordered = [records[key] for key in sorted(records)]
    else:
        ordered = sorted(records, key=lambda item: item.message_id)
    if not ordered:
        return None

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / TB_METADATA_JSON
    previous = _metadata_rows(json_path)
    merged = {key_from_row(row, "NOTICE").serialize(): row for row in previous}
    for record in ordered:
        key = record.record_key
        row = {**merged.get(key, {}), **record.to_dict()}
        # Tra cứu/dry-run không được xoá tham chiếu file đã tải lần trước.
        if not record.tep_pdf and key in merged:
            row["tep_pdf"] = merged[key].get("tep_pdf", "")
        merged[key] = row
    rows = [merged[key] for key in sorted(merged)]
    _atomic_write(json_path, json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"))
    generation(json_path, [], ready=False)
    if not materialize:
        return directory / TB_METADATA_CSV, json_path
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    csv_path = directory / TB_METADATA_CSV
    with StringIO(newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({key: csv_value(value) for key, value in row.items()} for row in rows)
        csv_bytes = stream.getvalue().encode("utf-8-sig")
    _atomic_write(csv_path, csv_bytes)
    write_tb_excel_report(directory / TB_METADATA_XLSX, rows)
    generation(json_path, [csv_path, directory / TB_METADATA_XLSX], ready=True)
    return csv_path, json_path


def write_tb_excel_report(path: str | Path, rows: Iterable[Mapping[str, object]]) -> Path:
    """Xuất bảng tổng hợp thông báo, an toàn với công thức từ dữ liệu ngoài."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Danh sách thông báo"
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
        table = Table(displayName="DanhSachThongBao", ref=sheet.dimensions)
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
            not isinstance(row, dict)
            or not isinstance(row.get("message_id"), str)
            or not row["message_id"]
            for row in rows
        ):
            raise ValueError("metadata thông báo phải là danh sách có message_id")
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
    "TbStore",
    "write_tb_excel_report",
    "write_tb_metadata",
]
