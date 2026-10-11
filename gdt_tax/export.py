"""Xuất và truy vấn dữ liệu đã parse (stage 08).

Đọc `manifest_artifact.json`, `parsed_declarations.json` và
`phan_loai_artifact.json` rồi xuất:

* workbook Excel nhiều sheet (index, GTGT, TNCN, TNDN, OTHER, unmapped, lỗi,
  mapping version, audit log);
* CSV/JSON có bộ lọc (tax_group, form, version, period, filing, status).

Không đưa logic portal vào đây, không cần credential/OCR/mạng. Giữ nguyên
provenance (`record_id`, `source_zip`, `source_inner_file`, `source_sha256`,
`xpath`), phân biệt NULL với 0, và **không** tự chọn bản bổ sung mới nhất hay
cộng dồn nhiều lần nộp cùng kỳ.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from .classify import CLASSIFICATION_NAME
from .errors import GdtError
from .inventory import MANIFEST_NAME
from .logging_setup import configure_streams
from .parser.cli import PARSED_NAME

LOGGER_NAME = "gdt_tax.export"
EXPORT_VERSION = "excel-export-v1"
WORKBOOK_NAME = "Tax_Return_Summary.xlsx"

INDEX_COLUMNS = (
    ("record_id", "record_id"),
    ("tax_type", "Nhóm thuế"),
    ("form_code", "Mã mẫu"),
    ("form_name", "Tên mẫu"),
    ("form_version", "Phiên bản mẫu"),
    ("taxpayer_tax_code", "MST"),
    ("taxpayer_name", "Tên NNT"),
    ("period_raw", "Kỳ tính thuế"),
    ("period_type", "Kiểu kỳ"),
    ("filing_type", "Loại nộp"),
    ("supplement_number", "Lần bổ sung"),
    ("status", "Trạng thái parse"),
    ("mapping_id", "Mapping"),
    ("source_zip", "File ZIP nguồn"),
    ("source_inner_file", "File trong ZIP"),
    ("source_sha256", "SHA-256"),
)

#: Sheet theo nhóm thuế; các nhóm không có sheet riêng gộp vào OTHER.
GROUP_SHEETS = (("02_GTGT", "GTGT"), ("03_TNCN", "TNCN"), ("04_TNDN", "TNDN"))


def record_id(source_sha256: str | None, artifact_id: str | None) -> str:
    """ID nội bộ ổn định theo hash nguồn + artifact (không dùng số thứ tự)."""
    basis = f"{source_sha256 or ''}\x00{artifact_id or ''}"
    return hashlib.sha256(basis.encode()).hexdigest()


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _classification_index(payload: dict | None) -> dict[str, dict]:
    if not payload:
        return {}
    return {
        item["artifact_id"]: item
        for item in payload.get("classifications", [])
        if isinstance(item, dict) and item.get("artifact_id")
    }


def build_rows(
    manifest: dict | None,
    parsed: dict | None,
    classification: dict | None,
) -> list[dict]:
    """Ghép manifest + parsed + classification thành danh sách dòng tờ khai."""
    class_by_id = _classification_index(classification)
    sha_by_id: dict[str, str | None] = {}
    if manifest:
        for container in manifest.get("containers", []):
            for artifact in container.get("members", []):
                sha_by_id[artifact.get("artifact_id", "")] = artifact.get("sha256")

    rows: list[dict] = []
    for declaration in (parsed or {}).get("declarations", []):
        if not isinstance(declaration, dict):
            continue
        artifact_id = declaration.get("artifact_id") or ""
        cls = class_by_id.get(artifact_id, {})
        sha = declaration.get("source_sha256") or sha_by_id.get(artifact_id)
        row = {
            "record_id": record_id(sha, artifact_id),
            "tax_type": cls.get("tax_group") or declaration.get("tax_type_hint") or "UNKNOWN",
            "form_code": declaration.get("form_code"),
            "form_name": declaration.get("form_name"),
            "form_version": declaration.get("form_version"),
            "taxpayer_tax_code": (declaration.get("taxpayer") or {}).get("tax_code"),
            "taxpayer_name": (declaration.get("taxpayer") or {}).get("name"),
            "period_raw": (declaration.get("period") or {}).get("raw"),
            "period_type": (declaration.get("period") or {}).get("period_type"),
            "filing_type": declaration.get("filing_type"),
            "supplement_number": declaration.get("supplement_number"),
            "status": declaration.get("status"),
            "mapping_id": declaration.get("mapping_id"),
            "source_zip": declaration.get("source_zip"),
            "source_inner_file": declaration.get("source_inner_file"),
            "source_sha256": sha,
            "document_role": cls.get("document_role") or "UNKNOWN",
            "classification_status": cls.get("status") or "UNKNOWN",
        }
        row["indicators"] = declaration.get("indicators", [])
        rows.append(row)
    return rows


def filter_rows(
    rows: list[dict],
    *,
    tax_group: str | None = None,
    form_code: str | None = None,
    form_version: str | None = None,
    period: str | None = None,
    filing_type: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """Lọc không làm mất lịch sử: chỉ thu hẹp tập hiển thị."""
    result = rows
    if tax_group:
        result = [r for r in result if r.get("tax_type") == tax_group]
    if form_code:
        result = [r for r in result if r.get("form_code") == form_code]
    if form_version:
        result = [r for r in result if r.get("form_version") == form_version]
    if period:
        result = [r for r in result if r.get("period_raw") == period]
    if filing_type:
        result = [r for r in result if r.get("filing_type") == filing_type]
    if status:
        result = [r for r in result if r.get("status") == status]
    return result


def _excel_safe(value: object) -> object:
    """Không để text từ nguồn bị Excel hiểu là công thức.

    Chỉ escape chuỗi **không phải số**: tiền âm như ``-100`` là số hợp lệ, phải
    giữ nguyên (spec §33, stage 08). Chuỗi bắt đầu ``=,+,-,@`` mà không phải số
    mới bị thêm tiền tố ``'``.
    """
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        try:
            Decimal(value)
        except InvalidOperation:
            return f"'{value}"
    return value


def _write_table_sheet(workbook: Workbook, title: str, rows: list[dict]) -> None:
    sheet = workbook.create_sheet(title)
    sheet.freeze_panes = "A2"
    headers = [label for _, label in INDEX_COLUMNS]
    sheet.append(headers)
    for row in rows:
        sheet.append([_excel_safe(row.get(key)) for key, _ in INDEX_COLUMNS])
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    if sheet.max_row > 1:
        table = Table(displayName=f"T_{title}", ref=sheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showRowStripes=True, showColumnStripes=False,
            showFirstColumn=False, showLastColumn=False,
        )
        sheet.add_table(table)
    sheet.auto_filter.ref = sheet.dimensions


def _write_indicators_sheet(workbook: Workbook, rows: list[dict]) -> None:
    """Chỉ tiêu dạng *dài* (long format) cho truy vấn/pivot; giữ XPath provenance."""
    sheet = workbook.create_sheet("05_INDICATORS")
    headers = [
        "record_id", "tax_type", "form_code", "form_version", "MST", "Kỳ tính thuế",
        "filing_type", "supplement_number", "canonical_name", "indicator_code",
        "display_name", "value", "raw_value", "status", "xpath",
    ]
    sheet.append(headers)
    for row in rows:
        for indicator in row.get("indicators", []):
            sheet.append([
                row["record_id"], row["tax_type"], row["form_code"], row["form_version"],
                row["taxpayer_tax_code"], row["period_raw"], row["filing_type"],
                row["supplement_number"],
                _excel_safe(indicator.get("canonical_name")),
                _excel_safe(indicator.get("code")),
                _excel_safe(indicator.get("display_name")),
                _excel_safe(indicator.get("value")),
                _excel_safe(indicator.get("raw_value")),
                indicator.get("status"),
                _excel_safe(indicator.get("xpath")),
            ])
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.font = Font(color="FFFFFF", bold=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def _write_rows_sheet(workbook: Workbook, title: str, headers: list[str], rows: list[list]) -> None:
    sheet = workbook.create_sheet(title)
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.font = Font(color="FFFFFF", bold=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def build_workbook(
    rows: list[dict],
    manifest: dict | None,
    parsed: dict | None,
    classification: dict | None,
) -> Workbook:
    workbook = Workbook()
    workbook.remove(workbook.active)

    readme = workbook.create_sheet("00_README")
    for line in (
        ["Tax Return Summary", ""]
        + [f"- {label}: {value}" for label, value in _audit_summary(rows, manifest, parsed, classification).items()]
        + [
            "",
            "Chỉ tiêu tổng hợp nằm ở sheet 05_INDICATORS (dạng dài, kèm XPath truy vết).",
            "NULL (ô trống) khác 0: ô trống nghĩa là chỉ tiêu không có/không tìm thấy.",
            "Mỗi dòng giữ record_id, source_zip, source_inner_file, source_sha256 để truy ngược.",
        ]
    ):
        readme.append([line])

    _write_table_sheet(workbook, "01_RETURN_INDEX", rows)
    for title, group in GROUP_SHEETS:
        _write_table_sheet(workbook, title, [r for r in rows if r["tax_type"] == group])
    _write_table_sheet(
        workbook, "06_OTHER_RETURNS",
        [r for r in rows if r["tax_type"] not in {g for _, g in GROUP_SHEETS} and r["tax_type"] != "UNKNOWN"],
    )
    _write_indicators_sheet(workbook, rows)

    unmapped = [r for r in rows if r["status"] != "MAPPED"]
    _write_rows_sheet(
        workbook, "07_UNMAPPED_FORMS",
        ["record_id", "form_code", "form_version", "tax_type", "MST", "Kỳ tính thuế", "status", "source_zip"],
        [[r["record_id"], r["form_code"], r["form_version"], r["tax_type"], r["taxpayer_tax_code"], r["period_raw"], r["status"], r["source_zip"]] for r in unmapped],
    )
    errors = [r for r in rows if r["status"] == "error"]
    _write_rows_sheet(
        workbook, "08_PARSE_ERRORS",
        ["record_id", "source_zip", "source_inner_file", "status"],
        [[r["record_id"], r["source_zip"], r["source_inner_file"], r["status"]] for r in errors],
    )
    mapping_versions = sorted({r["mapping_id"] for r in rows if r["mapping_id"]})
    _write_rows_sheet(
        workbook, "09_MAPPING_VERSIONS", ["mapping_id"], [[m] for m in mapping_versions],
    )
    summary = _audit_summary(rows, manifest, parsed, classification)
    _write_rows_sheet(
        workbook, "10_AUDIT_LOG", ["Chỉ số", "Giá trị"],
        [[k, _excel_safe(v)] for k, v in summary.items()],
    )
    return workbook


def _audit_summary(rows, manifest, parsed, classification) -> dict:
    tax = Counter(r["tax_type"] for r in rows)
    status = Counter(r["status"] for r in rows)
    return {
        "export_version": EXPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "containers": len((manifest or {}).get("containers", [])),
        "declarations": len(rows),
        "gtgt": tax.get("GTGT", 0),
        "tncn": tax.get("TNCN", 0),
        "tndn": tax.get("TNDN", 0),
        "other": sum(v for k, v in tax.items() if k not in {"GTGT", "TNCN", "TNDN", "UNKNOWN"}),
        "unknown_tax_group": tax.get("UNKNOWN", 0),
        "mapped": status.get("MAPPED", 0),
        "need_mapping": status.get("NEED_MAPPING", 0),
        "errors": status.get("error", 0),
        "classifications": (classification or {}).get("count", 0),
        "parser_version": (parsed or {}).get("parser_version"),
    }


def write_workbook(workbook: Workbook, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with BytesIO() as stream:
        workbook.save(stream)
        payload = stream.getvalue()
    workbook.close()
    _atomic_write(path, payload)
    return path


def _atomic_write(path: Path, data: bytes) -> None:
    import os
    import tempfile

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
        raise GdtError(f"Không ghi được {path}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_csv(path: Path, rows: list[dict]) -> Path:
    fieldnames = [key for key, _ in INDEX_COLUMNS]
    with StringIO(newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
        data = stream.getvalue().encode("utf-8-sig")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, data)
    return path


def load_inputs(folder: Path) -> tuple[dict | None, dict | None, dict | None]:
    return (
        _read_json(folder / MANIFEST_NAME),
        _read_json(folder / PARSED_NAME),
        _read_json(folder / CLASSIFICATION_NAME),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gdt-export",
        description="Xuất Excel/CSV/JSON từ manifest + parsed + classification (offline).",
    )
    parser.add_argument("folder", help="Thư mục chứa manifest/parsed/classification")
    parser.add_argument("--output", help="Thư mục ghi (mặc định: thư mục nguồn)")
    parser.add_argument("--tax-group", help="Lọc theo nhóm thuế")
    parser.add_argument("--form-code", help="Lọc theo mã mẫu")
    parser.add_argument("--form-version", help="Lọc theo phiên bản mẫu")
    parser.add_argument("--period", help="Lọc theo kỳ tính thuế (raw)")
    parser.add_argument("--filing-type", help="Lọc theo loại nộp")
    parser.add_argument("--status", help="Lọc theo trạng thái parse")
    parser.add_argument("--csv", help="Ghi thêm CSV vào đường dẫn này")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_streams()
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    log = logging.getLogger(LOGGER_NAME)
    folder = Path(args.folder)
    output = Path(args.output) if args.output else folder
    try:
        manifest, parsed, classification = load_inputs(folder)
        if parsed is None:
            raise GdtError(f"Chưa có {PARSED_NAME} trong {folder}; chạy gdt-parse trước")
        rows = build_rows(manifest, parsed, classification)
        filtered = filter_rows(
            rows,
            tax_group=args.tax_group,
            form_code=args.form_code,
            form_version=args.form_version,
            period=args.period,
            filing_type=args.filing_type,
            status=args.status,
        )
        workbook = build_workbook(filtered, manifest, parsed, classification)
        target = write_workbook(workbook, output / WORKBOOK_NAME)
        if args.csv:
            write_csv(Path(args.csv), filtered)
    except GdtError as error:
        log.error("%s", error)
        return 1
    log.info("Đã xuất %s dòng tờ khai", len(filtered))
    log.info("Workbook: %s", target)
    return 0


__all__ = [
    "EXPORT_VERSION",
    "INDEX_COLUMNS",
    "WORKBOOK_NAME",
    "build_rows",
    "build_workbook",
    "filter_rows",
    "load_inputs",
    "main",
    "record_id",
    "write_csv",
    "write_workbook",
]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
