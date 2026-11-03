"""Kiểu dữ liệu dùng chung giữa các module."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date


@dataclass
class CaseRecord:
    """Một hồ sơ (hoặc thông báo) tra cứu được từ legacy, ETAX hoặc DVC.

    Các nguồn trả số cột khác nhau nên một số trường để rỗng tùy nguồn;
    ``ten_tthc`` chỉ có ở nguồn DVC.
    """

    ma_ho_so: str
    nguon: str
    ten_tthc: str = ""
    to_khai: str = ""
    ky_tinh_thue: str = ""
    loai_to_khai: str = ""
    lan_nop: str = ""
    lan_bo_sung: str = ""
    ngay_nop: str = ""
    noi_nop: str = ""
    trang_thai: str = ""
    ho_so_dinh_kem: str = ""
    tep_zip: str = ""
    #: Mã số thuế/số định danh của người nộp thuế; điền sau khi đăng nhập.
    mst: str = ""
    ten_nguoi_nop_thue: str = ""
    #: Thông báo của cơ quan thuế: số văn bản và mã loại dùng khi tải tệp.
    so_thong_bao: str = ""
    ma_loai_thong_bao: str = ""
    #: Nhóm thuế khác với loai_to_khai (chính thức/bổ sung).
    nhom_to_khai: str = "UNKNOWN"
    loai_tai_lieu: str = "UNKNOWN"
    quy_tac_phan_loai: str = ""
    ly_do_phan_loai: str = ""

    def to_dict(self) -> dict[str, str]:
        """Chuyển sang ``dict`` để ghi CSV/JSON."""
        return asdict(self)


@dataclass(frozen=True)
class SearchPeriod:
    """Một đoạn tra cứu hợp lệ (tối đa 31 ngày) gắn với một nguồn dữ liệu."""

    start: date
    end: date
    source: str

    @property
    def label(self) -> str:
        return f"{self.start:%d/%m/%Y} - {self.end:%d/%m/%Y}"


@dataclass
class PageResult:
    """Kết quả một trang tra cứu."""

    records: list[CaseRecord] = field(default_factory=list)
    total_pages: int | None = None
    http_status: int = 0


@dataclass
class RunSummary:
    """Tổng kết một lần chạy."""

    downloaded: int = 0
    expected: int = 0
    periods: int = 0
    dry_run: bool = False
    discovered: int = 0
    skipped_periods: int = 0

    @property
    def complete(self) -> bool:
        return self.skipped_periods == 0 and self.downloaded == self.expected

    @property
    def search_complete(self) -> bool:
        return self.skipped_periods == 0 and self.discovered == self.expected
