"""Giấy nộp tiền (GNT) — kiểu dữ liệu dùng chung trong luồng GNT.

Một giấy nộp tiền không phải hồ sơ/tờ khai nên có model riêng, không dùng
:class:`gdt_tax.models.CaseRecord`. Công cụ **chỉ tải XML** của GNT, không parse
chỉ tiêu bên trong; các trường ở đây là những gì trang kết quả đã hiển thị sẵn.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta

from ..constants import SOURCE_GNT
from ..dates import parse_date
from ..identity import IDENTITY_VERSION, UNKNOWN, RecordKey
from ..models import SearchPeriod
from ..table_contracts import ParseDiagnostics


@dataclass
class GiayNopTien:
    """Một dòng giấy nộp tiền trên trang Thuế điện tử cũ (etaxnnt).

    ``ctu_id`` là mã nội bộ cổng dùng để tải XML (tham số ``ctuId`` của
    ``reportForm``); các trường còn lại sao chép từ bảng kết quả.
    """

    ctu_id: str
    so_tham_chieu: str = ""
    ma_giao_dich_chi_tiet: str = ""
    lan_nop: str = ""
    so_gnt: str = ""
    so_tien: str = ""
    loai_tien: str = ""
    trang_thai: str = ""
    so_chung_tu: str = ""
    ngay_lap: str = ""
    ngay_gui: str = ""
    ngay_nop: str = ""
    co_ds_chi_tiet_tncn: str = ""
    co_ds_chi_tiet_tmdt: str = ""
    ngay_nop_ds_chi_tiet: str = ""
    hinh_thuc_nop: str = ""
    ngan_hang: str = ""
    tai_khoan: str = ""
    thong_bao: str = ""
    #: Tên file XML đã tải (rỗng nếu chưa tải).
    tep_xml: str = ""
    account_key: str = UNKNOWN

    @property
    def key(self) -> RecordKey:
        return RecordKey(self.account_key, SOURCE_GNT, "GNT", self.ctu_id)

    @property
    def record_key(self) -> str:
        return self.key.serialize()

    def to_dict(self) -> dict[str, str]:
        """Chuyển sang ``dict`` để ghi CSV/JSON/Excel."""
        return {**asdict(self), "record_key": self.record_key, "identity_version": IDENTITY_VERSION}


@dataclass
class GntPageResult:
    """Kết quả một trang tra cứu giấy nộp tiền."""

    records: list[GiayNopTien] = field(default_factory=list)
    total_pages: int | None = None
    http_status: int = 0
    diagnostics: ParseDiagnostics | None = None


@dataclass
class GntSummary:
    """Tổng kết một lần chạy GNT."""

    discovered: int = 0
    downloaded: int = 0
    periods: int = 0
    dry_run: bool = False
    expected: int | None = None

    @property
    def complete(self) -> bool:
        return self.downloaded == (self.discovered if self.expected is None else self.expected)


def gnt_periods(start, end, max_days: int) -> list[SearchPeriod]:
    """Chia khoảng ngày thành các đoạn tối đa ``max_days`` ngày để tra cứu GNT."""
    if max_days < 1:
        raise ValueError("Số ngày tối đa mỗi lần tra cứu phải lớn hơn 0")
    first = parse_date(start)
    last = parse_date(end)
    if first > last:
        raise ValueError("Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc")
    periods: list[SearchPeriod] = []
    cursor = first
    while cursor <= last:
        chunk_end = min(last, cursor + timedelta(days=max_days - 1))
        periods.append(SearchPeriod(start=cursor, end=chunk_end, source=SOURCE_GNT))
        cursor = chunk_end + timedelta(days=1)
    return periods


__all__ = ["GiayNopTien", "GntPageResult", "GntSummary", "gnt_periods"]
