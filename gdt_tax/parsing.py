"""Đọc bảng kết quả trả về từ cổng Dịch vụ công.

Ba nguồn dữ liệu trả về bảng khác nhau. Thứ tự cột thật trên cổng:

ETAX — ``/tchs/thuedientu`` (11 cột)::

    0 STT | 1 Mã giao dịch | 2 Tờ khai/Phụ lục | 3 Kỳ tính thuế | 4 Loại tờ khai
    5 Lần nộp | 6 Lần bổ sung | 7 Ngày nộp | 8 Nơi nộp
    9 Tiến trình giải quyết (Trạng thái) | 10 Thao tác

DVC — ``/ho-so/search`` (13 cột)::

    0 STT | 1 Thao tác | 2 Mã hồ sơ | 3 Tên TTHC | 4 Tờ khai | 5 Kỳ tính thuế
    6 Loại tờ khai | 7 Lần nộp bổ sung | 8 Lần nộp | 9 Cơ quan thuế tiếp nhận
    10 Ngày nộp | 11 Trạng thái | 12 Hồ sơ đính kèm

ETAX_LEGACY — trang Thuế điện tử cũ ``thuedientu.gdt.gov.vn`` (12 cột)::

    0 STT | 1 Mã giao dịch | 2 Tờ khai/Phụ lục | 3 Kỳ tính thuế | 4 Loại tờ khai
    5 Lần nộp | 6 Lần bổ sung | 7 Ngày nộp | 8 (trống)
    9 Nơi nộp | 10 Trạng thái | 11 Thao tác (link downloadTkhai)

Mã hồ sơ ưu tiên lấy từ thuộc tính ``data-ma-ho-so`` của nút "Thao tác" vì đó
là dữ liệu cổng dùng cho các lệnh AJAX.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from .constants import ALL_SOURCES, SOURCE_DVC, SOURCE_ETAX, SOURCE_ETAX_LEGACY
from .csrf import attribute
from .models import CaseRecord

ETAX_MIN_CELLS = 10
DVC_MIN_CELLS = 12
ETAX_LEGACY_MIN_CELLS = 11
SOURCES = (SOURCE_ETAX, SOURCE_DVC)
LEGACY_RESULT_TABLE_ID = "data_content_onday"


def legacy_message_id(row_html: str, event: str = "downloadTkhai") -> str:
    """Lấy mã hồ sơ từ lệnh ``downloadTkhai('...')`` trong một hàng bảng legacy."""
    match = re.search(rf"{event}\(\s*['\"]([^'\"]+)['\"]", row_html)
    return match.group(1) if match else ""


def _check_source(source: str) -> None:
    """Chặn nguồn lạ.

    Không có bước này thì một nguồn mới (hoặc tên sai chính tả) sẽ lặng lẽ được
    đọc như DVC và cho ra hồ sơ sai cột thay vì báo lỗi ngay.
    """
    if source not in ALL_SOURCES:
        raise ValueError(
            f"Nguồn dữ liệu không hợp lệ: {source!r}. Chỉ có {', '.join(ALL_SOURCES)}"
        )


def direct_cells(row: Tag) -> list[str]:
    """Lấy text của các ``<td>`` trực tiếp trong một hàng."""
    return [cell.get_text(" ", strip=True) for cell in row.find_all("td", recursive=False)]


def case_id_from_row(row: Tag, cells: list[str], fallback_index: int) -> str:
    marker = row.find(lambda tag: tag.has_attr("data-ma-ho-so"))
    if marker:
        value = attribute(marker, "data-ma-ho-so")
        if value.strip():
            return value.strip()
    if len(cells) > fallback_index:
        return cells[fallback_index].strip()
    return ""


def etax_record(cells: list[str], case_id: str) -> CaseRecord | None:
    """Đọc một hàng bảng ETAX (11 cột) thành hồ sơ."""
    if not case_id or len(cells) < ETAX_MIN_CELLS:
        return None
    return CaseRecord(
        ma_ho_so=case_id,
        nguon=SOURCE_ETAX,
        to_khai=cells[2],
        ky_tinh_thue=cells[3],
        loai_to_khai=cells[4],
        lan_nop=cells[5],
        lan_bo_sung=cells[6],
        ngay_nop=cells[7],
        noi_nop=cells[8],
        trang_thai=cells[9],
    )


def dvc_record(cells: list[str], case_id: str) -> CaseRecord | None:
    """Đọc một hàng bảng DVC (13 cột) thành hồ sơ."""
    if not case_id or len(cells) < DVC_MIN_CELLS:
        return None
    return CaseRecord(
        ma_ho_so=case_id,
        nguon=SOURCE_DVC,
        ten_tthc=cells[3],
        to_khai=cells[4],
        ky_tinh_thue=cells[5],
        loai_to_khai=cells[6],
        lan_bo_sung=cells[7],
        lan_nop=cells[8],
        noi_nop=cells[9],
        ngay_nop=cells[10],
        trang_thai=cells[11],
    )


def etax_legacy_record(cells: list[str], row: Tag) -> CaseRecord | None:
    """Đọc một hàng bảng legacy (12 cột) thành hồ sơ.

    Mã hồ sơ nằm trong lệnh ``downloadTkhai('...')`` của cột Thao tác; hàng
    không có lệnh này (thông báo, tờ khai bị huỷ) được bỏ qua.
    """
    if len(cells) < ETAX_LEGACY_MIN_CELLS:
        return None
    row_html = str(row)
    case_id = legacy_message_id(row_html)
    if not case_id:
        return None
    return CaseRecord(
        ma_ho_so=case_id,
        nguon=SOURCE_ETAX_LEGACY,
        to_khai=cells[2],
        ky_tinh_thue=cells[3],
        loai_to_khai=cells[4],
        lan_nop=cells[5],
        lan_bo_sung=cells[6],
        ngay_nop=cells[7],
        noi_nop=cells[9],
        trang_thai=cells[10],
    )


def parse_records(html: str, source: str) -> list[CaseRecord]:
    """Đọc mọi hồ sơ trong bảng kết quả, bỏ trùng theo mã hồ sơ."""
    _check_source(source)
    soup = BeautifulSoup(html, "lxml")
    records: list[CaseRecord] = []
    seen: set[str] = set()

    if source == SOURCE_ETAX_LEGACY:
        table = soup.find("table", id=LEGACY_RESULT_TABLE_ID)
        if table is None:
            return records
        for row in table.find_all("tr"):
            cells = direct_cells(row)
            record = etax_legacy_record(cells, row)
            if record is None or record.ma_ho_so in seen:
                continue
            seen.add(record.ma_ho_so)
            records.append(record)
        return records

    for row in soup.select("tbody tr"):
        cells = direct_cells(row)
        if source == SOURCE_ETAX:
            case_id = case_id_from_row(row, cells, fallback_index=1)
            record = etax_record(cells, case_id)
        else:
            case_id = case_id_from_row(row, cells, fallback_index=2)
            record = dvc_record(cells, case_id)
        if record is None or record.ma_ho_so in seen:
            continue
        seen.add(record.ma_ho_so)
        records.append(record)
    return records


def _int_attribute(soup: BeautifulSoup, element_id: str, attribute_name: str) -> int | None:
    element = soup.find(id=element_id)
    if element is None:
        return None
    value = attribute(element, attribute_name).strip()
    return int(value) if value.isdigit() else None


def page_count(html: str, source: str) -> int | None:
    """Tổng số trang của kết quả tra cứu, ``None`` nếu cổng không cho biết."""
    _check_source(source)
    soup = BeautifulSoup(html, "lxml")
    if source == SOURCE_ETAX:
        return _int_attribute(soup, "goToPage_tdt", "max")

    total = soup.find(id="totalPage")
    if total and total.get_text(strip=True).isdigit():
        return int(total.get_text(strip=True))
    return _int_attribute(soup, "gotoPageInput", "max")


__all__ = [
    "DVC_MIN_CELLS",
    "ETAX_LEGACY_MIN_CELLS",
    "ETAX_MIN_CELLS",
    "LEGACY_RESULT_TABLE_ID",
    "SOURCES",
    "case_id_from_row",
    "direct_cells",
    "dvc_record",
    "etax_legacy_record",
    "etax_record",
    "legacy_message_id",
    "page_count",
    "parse_records",
]
