"""Lưu ZIP và xuất metadata.

Thư mục tải về chứa:

* các file ``*.zip`` do cổng trả về
* ``danh_sach_ho_so.csv`` (UTF-8 BOM, mở tốt bằng Excel)
* ``danh_sach_ho_so.json``
* ``danh_sach_to_khai.xlsx`` (báo cáo đã định dạng để mở bằng Excel)

ZIP đã tải hợp lệ sẽ được bỏ qua ở lần chạy sau, nên có thể chạy tiếp khi bị gián đoạn.
"""

from __future__ import annotations

import base64
import csv
import glob
import json
import logging
import zipfile
from collections.abc import Iterable, Mapping
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from .constants import METADATA_CSV, METADATA_JSON, METADATA_XLSX
from .models import CaseRecord
from .naming import zip_filename

LOGGER_NAME = "gdt_tax.storage"

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

EXCEL_WIDTHS = (7, 32, 58, 16, 20, 18, 12, 42, 22, 48, 18)


def valid_zip(data: bytes) -> bool:
    """Kiểm tra dữ liệu có phải ZIP nguyên vẹn (không chỉ có chữ ký ``PK``)."""
    if not data.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            return archive.testzip() is None
    except (zipfile.BadZipFile, OSError):
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
        # glob.escape: mã hồ sơ có thể chứa ký tự đặc biệt (``[``, ``?``, ``*``).
        pattern = f"*{glob.escape(record.ma_ho_so)}*.zip"
        candidates = [preferred, *self.directory.glob(pattern)]
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
        path.write_bytes(data)
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
    """Xuất Excel cùng metadata CSV/JSON; trả ``None`` nếu chưa có hồ sơ nào."""
    if isinstance(records, Mapping):
        ordered = [records[key] for key in sorted(records)]
    else:
        ordered = sorted(records, key=lambda item: item.ma_ho_so)
    if not ordered:
        return None

    rows = [record.to_dict() for record in ordered]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    csv_path = directory / METADATA_CSV
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    json_path = directory / METADATA_JSON
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_excel_report(directory / METADATA_XLSX, ordered)
    return csv_path, json_path


def write_excel_report(path: str | Path, records: Iterable[CaseRecord]) -> Path:
    """Ghi báo cáo tờ khai ``.xlsx`` với đúng các cột nghiệp vụ từ bảng TCHS."""
    ordered = list(records)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Danh sách tờ khai"
    sheet.append([label for label, _attribute in EXCEL_COLUMNS])

    for index, record in enumerate(ordered, start=1):
        sheet.append(
            [
                index if attribute is None else getattr(record, attribute)
                for _label, attribute in EXCEL_COLUMNS
            ]
        )

    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 32

    for column, width in enumerate(EXCEL_WIDTHS, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=column).column_letter].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            # Nội dung do cổng trả về là dữ liệu, không phải công thức Excel.
            # Ép chuỗi để các giá trị bắt đầu bằng =, +, - hoặc @ không bị chạy.
            if isinstance(cell.value, str):
                cell.data_type = "s"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        row[0].alignment = Alignment(horizontal="center", vertical="top")

    last_row = max(2, len(ordered) + 1)
    if ordered:
        table = Table(displayName="DanhSachToKhai", ref=f"A1:K{last_row}")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)
    else:
        sheet.auto_filter.ref = "A1:K1"

    sheet.freeze_panes = "A2"
    sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_title_rows = "1:1"
    workbook.save(path)
    return path


__all__ = [
    "ZipStore",
    "decode_zip_bytes",
    "valid_zip",
    "write_excel_report",
    "write_metadata",
]
