"""Named portal table contracts and explicit evidence for empty/partial pages."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup, Tag

TABLE_CONTRACT_VERSION = "portal-table-v1"


def normalize_label(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"[^a-z0-9]+", "", "".join(c for c in value.casefold() if not unicodedata.combining(c)))


@dataclass
class ParseDiagnostics:
    status: str = "SCHEMA_CHANGED"
    candidate_count: int = 0
    parsed_count: int = 0
    skipped_count: int = 0
    duplicate_count: int = 0
    reasons: list[str] = field(default_factory=list)
    # Private per-row evidence. Never interpolate raw values into a log message.
    row_issues: list[dict] = field(default_factory=list)
    contract_version: str = TABLE_CONTRACT_VERSION
    schema_fingerprint: str = ''

    @property
    def complete(self) -> bool:
        return self.status in {"PARSED", "EMPTY_CONFIRMED"}


@dataclass
class TableParse:
    records: list[Any] = field(default_factory=list)
    diagnostics: ParseDiagnostics = field(default_factory=ParseDiagnostics)


@dataclass(frozen=True)
class TableSchema:
    name: str
    fields: tuple[str, ...]
    labels: tuple[str, ...]
    table_id: str = ""
    container: str = ""
    empty_form: str = ""
    empty_markers: tuple[str, ...] = ()
    date_fields: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()

    @property
    def aliases(self) -> dict[str, str]:
        aliases = {normalize_label(label): name for name, label in zip(self.fields, self.labels, strict=True) if name and label}
        aliases.update({normalize_label(name): name for name in self.fields if name})
        for label, name in COMMON_ALIASES.items():
            if name in self.fields:
                aliases[normalize_label(label)] = name
        return aliases


COMMON_ALIASES = {
    "Mã giao dịch": "ma_ho_so", "Mã hồ sơ": "ma_ho_so",
    "Tờ khai/Phụ lục": "to_khai", "Tên tờ khai": "to_khai", "Tờ khai": "to_khai",
    "Lần bổ sung": "lan_bo_sung", "Lần nộp bổ sung": "lan_bo_sung",
    "Nơi nộp": "noi_nop", "Cơ quan thuế tiếp nhận": "noi_nop",
    "Trạng thái": "trang_thai", "Tiến trình giải quyết hồ sơ (Trạng thái)": "trang_thai",
    "Ngày gửi": "ngay_gui", "Ngày gửi thông báo": "ngay_gui",
}

TAX_FIELDS = ("stt", "ma_ho_so", "to_khai", "ky_tinh_thue", "loai_to_khai", "lan_nop",
              "lan_bo_sung", "ngay_nop", "noi_nop", "trang_thai", "actions")
TAX_LABELS = ("STT", "Mã giao dịch", "Tờ khai/Phụ lục", "Kỳ tính thuế", "Loại tờ khai",
              "Lần nộp", "Lần bổ sung", "Ngày nộp", "Nơi nộp", "Trạng thái", "Thao tác")
SCHEMAS = {
    "ETAX": TableSchema("ETAX", TAX_FIELDS, TAX_LABELS, container=".bangKetQuaTraCuu_tdt",
        empty_markers=("Không có dữ liệu", "Không tìm thấy hồ sơ"), date_fields=("ngay_nop",)),
    "DVC": TableSchema("DVC", ("stt", "actions", "ma_ho_so", "ten_tthc", "to_khai", "ky_tinh_thue",
        "loai_to_khai", "lan_bo_sung", "lan_nop", "noi_nop", "ngay_nop", "trang_thai", "ho_so_dinh_kem"),
        ("STT", "Thao tác", "Mã hồ sơ", "Tên TTHC", "Tờ khai", "Kỳ tính thuế", "Loại tờ khai",
         "Lần nộp bổ sung", "Lần nộp", "Cơ quan thuế tiếp nhận", "Ngày nộp", "Trạng thái", "Hồ sơ đính kèm"),
        container="#table-container", empty_markers=("Không có dữ liệu", "Không tìm thấy hồ sơ"),
        date_fields=("ngay_nop",), optional=("ho_so_dinh_kem",)),
    "ETAX_LEGACY": TableSchema("ETAX_LEGACY", (*TAX_FIELDS[:8], "", *TAX_FIELDS[8:]),
        (*TAX_LABELS[:8], "", *TAX_LABELS[8:]), table_id="data_content_onday", empty_form="traCuuKhaiForm",
        empty_markers=("Chưa có tờ khai nào được gửi thỏa mãn điều kiện tra cứu trên",), date_fields=("ngay_nop",)),
    "GNT": TableSchema("GNT", ("stt", "so_tham_chieu", "ma_giao_dich_chi_tiet", "lan_nop", "so_gnt",
        "so_tien", "loai_tien", "trang_thai", "so_chung_tu", "ngay_lap", "ngay_gui", "ngay_nop",
        "co_ds_chi_tiet_tncn", "co_ds_chi_tiet_tmdt", "ngay_nop_ds_chi_tiet", "hinh_thuc_nop", "ngan_hang", "tai_khoan", "actions", "thong_bao"),
        ("STT", "Số tham chiếu/ Mã giao dịch", "Mã giao dịch DS chi tiết", "Lần nộp", "Số giấy nộp tiền",
        "Số tiền", "Loại tiền", "Trạng thái", "Số chứng từ", "Ngày lập GNT", "Ngày gửi GNT", "Ngày nộp thuế",
        "Nộp DS chi tiết TNCN", "Nộp DS chi tiết TMĐT", "Ngày nộp DS chi tiết", "Hình thức nộp", "Ngân hàng", "Tài khoản ngân hàng", "#", "Thông báo"),
        table_id="data_content_onday", empty_form="reportForm", empty_markers=("Chưa có giấy nộp tiền", "Không có dữ liệu", "không có giấy nộp tiền"),
        date_fields=("ngay_lap", "ngay_gui", "ngay_nop", "ngay_nop_ds_chi_tiet")),
    "TB": TableSchema("TB", ("stt", "ma_thong_bao", "ten_thong_bao", "so_thong_bao", "ngay_gui", "co_quan_gui", "trang_thai", "co_van_ban_giai_trinh", "co_phan_hoi_ra_soat", "actions"),
        ("STT", "Mã thông báo", "Tên thông báo", "Số thông báo", "Ngày gửi thông báo", "Cơ quan gửi", "Trạng thái", "Văn bản giải trình điện tử", "Phản hồi kết quả rà soát", "Tải thông báo"),
        table_id="tbl_tracuu", empty_form="tKhaiForm", empty_markers=("Không tìm thấy thông báo", "không có thông báo", "Chưa có thông báo", "Không có dữ liệu"), date_fields=("ngay_gui",)),
}


def _header_map(table: Tag, schema: TableSchema) -> tuple[dict[str, int], list[Tag], int]:
    thead = table.find("thead", recursive=False)
    rows = thead.find_all("tr") if thead else [row for row in table.find_all("tr")
             if row.find_parent("table") is table and row.find("th", recursive=False)]
    if not rows:
        return {}, [], 0
    if len(rows) > 20:
        return {}, rows, -1
    grid: dict[tuple[int, int], str] = {}
    for y, row in enumerate(rows[:20]):
        x = 0
        for cell in row.find_all(["th", "td"], recursive=False):
            while (y, x) in grid:
                x += 1
            try:
                width, height = int(str(cell.get("colspan", "1"))), int(str(cell.get("rowspan", "1")))
            except (TypeError, ValueError):
                return {}, rows, -1
            if not 1 <= width <= 100 or not 1 <= height <= 20:
                return {}, rows, -1
            label = str(cell.get("data-field") or cell.get("data-column") or cell.get_text(" ", strip=True))
            for dy in range(height):
                for dx in range(width):
                    grid[y + dy, x + dx] = label
            x += width
            if x > 100:
                return {}, rows, -1
    width = max((x + 1 for _, x in grid), default=0)
    mapped = {}
    for x in range(width):
        label = next((grid[y, x] for y in reversed(range(len(rows))) if (y, x) in grid), "")
        key = schema.aliases.get(normalize_label(label))
        if key:
            if key in mapped:
                return {}, rows, -1
            mapped[key] = x
    return mapped, rows, width


def _known_empty(soup: BeautifulSoup, schema: TableSchema) -> bool:
    scope = soup.select_one(schema.container) if schema.container else soup
    if scope is None:
        return False
    if schema.empty_form and not _has_form(soup, schema):
        return False
    for script in scope.find_all(["script", "style"]):
        script.decompose()
    text = normalize_label(scope.get_text(" ", strip=True))
    return any(normalize_label(marker) in text for marker in schema.empty_markers)


def _has_form(soup: BeautifulSoup, schema: TableSchema) -> bool:
    operations = {"GNT": "corpQueryTaxProc", "TB": "tracuuTBThueKhacProc", "ETAX_LEGACY": "traCuuToKhaiProc"}
    operation = operations.get(schema.name)
    return any(form.find("input", attrs={"name": "dse_operationName", "value": operation}) is not None
               for form in soup.find_all("form")) if operation else False


def _headerless_fingerprint(soup: BeautifulSoup, schema: TableSchema, nodes: list[Tag], raw: list[str]) -> bool:
    if len(raw) != len(schema.fields) or not raw[0].isdigit():
        return False
    if schema.name == "ETAX":
        marker = nodes[10].find(None, attrs={"data-ma-ho-so": True})
        return marker is not None and str(marker.get("data-ma-ho-so")) == raw[1] and raw[5].isdigit() and raw[6].isdigit()
    if not _has_form(soup, schema):
        return False
    if schema.name == "ETAX_LEGACY":
        match = re.search(r"downloadTkhai\(\s*['\"]([^'\"]+)['\"]", str(nodes[11]))
        return bool(match and match.group(1) == raw[1] and raw[5].isdigit() and raw[6].isdigit() and not raw[8])
    if schema.name == "GNT":
        detail = re.search(r"chiTietCT\(\s*['\"]?(\d+)", str(nodes[4]))
        download = re.search(r"downloadGNT\(\s*['\"]?(\d+)", str(nodes[18]))
        return bool(detail and download and detail.group(1) == download.group(1)
                    and re.fullmatch(r"[A-Z]{3}", raw[6]) and raw[9])
    if schema.name == "TB":
        download = re.search(r"layFileTBao\(\s*['\"]([^'\"]+)['\"]", str(nodes[9]))
        status = nodes[6].find(id=re.compile(r"^updateStatus@"))
        return bool(download and status and str(status.get("id")) == "updateStatus@" + download.group(1) and raw[4])
    return False


def parse_table(html: str, schema: TableSchema, decoder: Callable[[Tag, list[str]], Any],
                identity: Callable[[Any], str]) -> TableParse:
    soup = BeautifulSoup(html, "lxml")
    result = TableParse()
    from .schema_evidence import safe_schema_evidence
    result.diagnostics.schema_fingerprint = safe_schema_evidence(html).get('fingerprint', '')
    diagnostics = result.diagnostics
    if soup.find("table") is None:
        for node in soup.find_all(["script", "style"]):
            node.decompose()
        visible = normalize_label(soup.get_text(" ", strip=True))
        if any(normalize_label(marker) in visible for marker in (
                "CAPTCHA rejected", "CAPTCHA không đúng", "Mã xác nhận không đúng", "Mã xác thực không đúng")):
            diagnostics.status = "CAPTCHA_INVALID"
            diagnostics.reasons.append("CAPTCHA_INVALID")
            return result
    tables: list[Tag]
    if schema.table_id:
        tables = list(soup.find_all("table", id=schema.table_id))
    else:
        scope = soup.select_one(schema.container) if schema.container else None
        candidates = (scope or soup).find_all("table")
        tables = [table for table in candidates if len(_header_map(table, schema)[0]) >= 3
                  or table.find(None, attrs={"data-ma-ho-so": True}) is not None]
        if not tables and scope is not None:
            tables = candidates
    if len(tables) != 1:
        if not tables and _known_empty(soup, schema):
            diagnostics.status = "EMPTY_CONFIRMED"
        else:
            diagnostics.reasons.append("RESULT_TABLE_MISSING_OR_AMBIGUOUS")
        return result
    table = tables[0]
    mapping, headers, width = _header_map(table, schema)
    required = {name for name in schema.fields if name and name not in schema.optional}
    # Headerless compatibility is allowed only with the row fingerprint below.
    header_problem = bool(headers and (width < 0 or not required.issubset(mapping)))
    header_reason = "REQUIRED_COLUMNS_MISSING_OR_AMBIGUOUS:" + ",".join(sorted(required - mapping.keys()))
    seen: dict[str, Any] = {}
    for row_index, row in enumerate(table.find_all("tr"), 1):
        if row in headers or row.find_parent("table") is not table:
            continue
        nodes = row.find_all("td", recursive=False)
        if not nodes or not any(node.get_text(strip=True) or node.find(True) for node in nodes):
            continue
        if len(nodes) == 1 and any(normalize_label(marker) in normalize_label(row.get_text(" ", strip=True)) for marker in schema.empty_markers):
            continue
        diagnostics.candidate_count += 1
        raw = [node.get_text(" ", strip=True) for node in nodes]
        local_map: dict[str, int] = {}
        for index, node in enumerate(nodes):
            name = schema.aliases.get(normalize_label(str(node.get("data-field") or node.get("data-column") or "")))
            if name:
                if name in local_map:
                    local_map = {}
                    break
                local_map[name] = index
        attributes_complete = required.issubset(local_map)
        selected = local_map if attributes_complete else mapping
        error = None
        if any(str(node.get("colspan", "1")) != "1" or str(node.get("rowspan", "1")) != "1" for node in nodes):
            error = "DATA_CELL_SPAN_UNSUPPORTED"
        elif headers and not attributes_complete and (header_problem or len(raw) != width):
            error = header_reason if header_problem else "ROW_SCHEMA_MISMATCH"
        elif selected:
            cells = [raw[selected[name]] if name in selected and selected[name] < len(raw) else "" for name in schema.fields]
        else:
            cells = raw
            if not _headerless_fingerprint(soup, schema, nodes, raw):
                error = "HEADERLESS_SCHEMA_UNVERIFIED"
        if error is None:
            values = dict(zip(schema.fields, cells, strict=True))
            for name in ("lan_nop", "lan_bo_sung"):
                if values.get(name) and not values[name].isdigit():
                    error = "INVALID_COUNTER_COLUMN:" + name
                    break
            for name in schema.date_fields:
                value = values.get(name, "")
                if value:
                    try:
                        datetime.strptime(value[:10], "%d/%m/%Y")
                    except ValueError:
                        error = "INVALID_DATE_COLUMN:" + name
                        break
            if schema.name == "GNT" and values.get("so_tien") and not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)*", values["so_tien"].replace(" ", "")):
                error = "INVALID_AMOUNT_COLUMN:so_tien"
        record = decoder(row, cells) if error is None else None
        if record is None:
            diagnostics.skipped_count += 1
            diagnostics.row_issues.append({"row": row_index, "code": error or "RECORD_HANDLER_OR_ID_MISSING", "raw_cells": raw})
            continue
        key = identity(record)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/\-]*", key):
            diagnostics.skipped_count += 1
            diagnostics.row_issues.append({"row": row_index, "code": "REMOTE_ID_SHAPE_INVALID", "raw_cells": raw})
            continue
        diagnostics.parsed_count += 1
        if key in seen:
            diagnostics.duplicate_count += 1
            if record != seen[key]:
                diagnostics.reasons.append("DUPLICATE_ID_CONFLICT")
            continue
        seen[key] = record
        result.records.append(record)
    if diagnostics.skipped_count or diagnostics.reasons:
        diagnostics.reasons.extend(sorted({item["code"] for item in diagnostics.row_issues}))
    elif diagnostics.candidate_count:
        diagnostics.status = "PARSED"
    elif _known_empty(soup, schema):
        diagnostics.status = "EMPTY_CONFIRMED"
    else:
        diagnostics.reasons.append(header_reason if header_problem else "EMPTY_NOT_CONFIRMED")
    return result
