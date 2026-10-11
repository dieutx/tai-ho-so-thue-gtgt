"""Thông báo của cơ quan thuế — kiểu dữ liệu dùng chung trong luồng TB.

Thông báo là văn bản do cơ quan thuế gửi (PDF trên trang Thuế điện tử cũ), không
phải hồ sơ nên có model riêng. Công cụ chỉ tải file về, không parse nội dung.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta

from ..constants import SOURCE_TB
from ..dates import parse_date
from ..models import SearchPeriod


@dataclass
class ThongBao:
    """Một dòng thông báo của cơ quan thuế."""

    #: Mã nội bộ cổng dùng để tải file (tham số ``messageId``).
    message_id: str
    #: Mã loại thông báo nội bộ cổng (tham số ``ma_tbao`` của lệnh tải).
    ma_tbao: str = ""
    ma_thong_bao: str = ""
    ten_thong_bao: str = ""
    so_thong_bao: str = ""
    ngay_gui: str = ""
    co_quan_gui: str = ""
    trang_thai: str = ""
    co_van_ban_giai_trinh: str = ""
    co_phan_hoi_ra_soat: str = ""
    #: Tên file PDF đã tải (rỗng nếu chưa tải).
    tep_pdf: str = ""

    def to_dict(self) -> dict[str, str]:
        """Chuyển sang ``dict`` để ghi CSV/JSON/Excel."""
        return asdict(self)


@dataclass
class TbPageResult:
    """Kết quả một trang tra cứu thông báo."""

    records: list[ThongBao] = field(default_factory=list)
    total_pages: int | None = None
    http_status: int = 0


@dataclass
class TbSummary:
    """Tổng kết một lần chạy thông báo."""

    discovered: int = 0
    downloaded: int = 0
    periods: int = 0
    dry_run: bool = False

    @property
    def complete(self) -> bool:
        return self.downloaded == self.discovered


def tb_periods(start, end, max_days: int) -> list[SearchPeriod]:
    """Chia khoảng ngày thành các đoạn tối đa ``max_days`` ngày để tra cứu TB."""
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
        periods.append(SearchPeriod(start=cursor, end=chunk_end, source=SOURCE_TB))
        cursor = chunk_end + timedelta(days=1)
    return periods


__all__ = ["TbPageResult", "TbSummary", "ThongBao", "tb_periods"]
