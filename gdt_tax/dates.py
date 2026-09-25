"""Quy tắc ngày tháng và chia khoảng tra cứu.

Cổng Dịch vụ công chỉ trả kết quả cho khoảng tra cứu **tối đa 31 ngày**, ở cả
luồng Thuế điện tử (ETAX, tờ khai nộp trước ``01/07/2025``) và luồng Dịch vụ
công (DVC). Người dùng có thể nhập khoảng dài; module này tự cắt thành các đoạn
hợp lệ và gắn nguồn dữ liệu tương ứng.

Muốn đổi mốc chuyển nguồn hoặc số ngày tối đa thì sửa hai hằng số dưới đây,
hoặc ghi đè bằng biến môi trường ``GDT_ETAX_CUTOFF`` / ``GDT_MAX_DAYS_PER_SEARCH``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

from .constants import SOURCE_DVC, SOURCE_ETAX
from .models import SearchPeriod

DATE_FORMAT = "%d/%m/%Y"
ETAX_CUTOFF_DEFAULT = date(2025, 7, 1)
MAX_DAYS_PER_SEARCH_DEFAULT = 31


def parse_date(value: str | date | datetime) -> date:
    """Đọc ngày dạng ``dd/mm/yyyy`` (hoặc giữ nguyên ``date``/``datetime``)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), DATE_FORMAT).date()
    except ValueError as error:
        raise ValueError(
            f"Ngày không hợp lệ: {value!r}. Định dạng đúng là dd/mm/yyyy"
        ) from error


def format_date(value: date) -> str:
    """Ghi ngày theo định dạng cổng Dịch vụ công chấp nhận."""
    return value.strftime(DATE_FORMAT)


def source_for(day: date, cutoff: date = ETAX_CUTOFF_DEFAULT) -> str:
    """Nguồn dữ liệu phù hợp với một ngày nộp hồ sơ."""
    return SOURCE_ETAX if day < cutoff else SOURCE_DVC


def split_periods(
    from_date: str | date,
    to_date: str | date,
    *,
    cutoff: date = ETAX_CUTOFF_DEFAULT,
    max_days: int = MAX_DAYS_PER_SEARCH_DEFAULT,
) -> Iterator[SearchPeriod]:
    """Chia khoảng ngày thành các đoạn tra cứu hợp lệ.

    Mỗi đoạn dài tối đa ``max_days`` ngày và không vượt qua mốc ``cutoff``, nhờ
    đó luồng ETAX không bao giờ bị cổng từ chối vì khoảng quá dài.
    """
    start = parse_date(from_date)
    end = parse_date(to_date)
    if start > end:
        raise ValueError("Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc")
    if max_days < 1:
        raise ValueError("Số ngày tối đa mỗi lần tra cứu phải lớn hơn 0")

    while start <= end:
        source = source_for(start, cutoff)
        # ETAX chỉ nhận hồ sơ trước mốc cutoff, nên đoạn ETAX dừng ngay trước mốc.
        source_end = cutoff - timedelta(days=1) if source == SOURCE_ETAX else end
        chunk_end = min(end, source_end, start + timedelta(days=max_days - 1))
        yield SearchPeriod(start=start, end=chunk_end, source=source)
        start = chunk_end + timedelta(days=1)
