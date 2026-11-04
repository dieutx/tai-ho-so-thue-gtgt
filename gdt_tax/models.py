"""Kiểu dữ liệu dùng chung giữa các module."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

from .identity import IDENTITY_VERSION, UNKNOWN, RecordKey
from .table_contracts import ParseDiagnostics


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
    trang_thai_tra_cuu: str = ""
    trang_thai_chi_tiet: str = ""
    trang_thai_cap_nhat: str = ""
    ho_so_dinh_kem: str = ""
    tep_zip: str = ""
    #: Nhóm thuế khác với loai_to_khai (chính thức/bổ sung).
    nhom_to_khai: str = "UNKNOWN"
    loai_tai_lieu: str = "UNKNOWN"
    quy_tac_phan_loai: str = ""
    ly_do_phan_loai: str = ""
    account_key: str = UNKNOWN
    attachment_status: str = 'NOT_REQUESTED'
    attachment_result: str = ''
    portal_profile_version: str = ''
    routing_version: str = ''

    @property
    def key(self) -> RecordKey:
        return RecordKey(self.account_key, self.nguon, "DECLARATION", self.ma_ho_so)

    @property
    def record_key(self) -> str:
        return self.key.serialize()

    def to_dict(self) -> dict[str, str]:
        """Chuyển sang ``dict`` để ghi CSV/JSON."""
        return {**asdict(self), "record_key": self.record_key, "identity_version": IDENTITY_VERSION}


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
    diagnostics: ParseDiagnostics | None = None


@dataclass
class RunSummary:
    """Tổng kết một lần chạy."""

    downloaded: int = 0
    expected: int = 0
    periods: int = 0
    dry_run: bool = False
    discovered: int = 0
    skipped_periods: int = 0
    attachments_complete: bool = True
    attachments_discovered: int = 0
    attachments_downloaded: int = 0
    attachments_reused: int = 0
    attachments_failed: int = 0
    routing_version: str = ''
    profile_versions: dict[str, str] = field(default_factory=dict)
    routing_issues: list[dict] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.primary_complete and self.attachments_complete

    @property
    def primary_complete(self) -> bool:
        return self.skipped_periods == 0 and self.downloaded == self.expected

    @property
    def search_complete(self) -> bool:
        return self.skipped_periods == 0 and self.discovered == self.expected
