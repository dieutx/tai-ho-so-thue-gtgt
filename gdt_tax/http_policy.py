"""Reviewed portal origins and bounded per-operation HTTP contracts."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .constants import LEGACY_ETAX_ORIGIN, ORIGIN
from .errors import NetworkError


def origin(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or "\\" in url or any(ord(char) < 32 for char in url)):
            raise ValueError("invalid origin")
        return f"https://{parsed.hostname.lower()}"
    except ValueError:
        raise NetworkError("HTTP_ORIGIN_REJECTED: URL must use a reviewed HTTPS origin") from None


@dataclass(frozen=True)
class OriginPolicy:
    allowed: frozenset[str] = frozenset({ORIGIN, LEGACY_ETAX_ORIGIN})

    def validate(self, url: str, *, previous: str | None = None) -> None:
        target = origin(url)
        if target not in self.allowed or (previous is not None and target != origin(previous)):
            raise NetworkError(f"HTTP_ORIGIN_REJECTED: {target}")


@dataclass(frozen=True)
class OperationPolicy:
    name: str = "portal"
    max_bytes: int = 64 * 1024 * 1024
    retry_safe: bool = False
    minimum_attempts: int = 1
    #: Hệ số tăng khoảng chờ giữa các lần thử lại khi cổng không gửi ``Retry-After``.
    #: 2.0 là lũy thừa (2/4/8/16/32s); endpoint bị giới hạn mạnh dùng hệ số nhỏ
    #: hơn để tổng thời gian chờ không phình ra khi cổng chặn dài.
    retry_growth: float = 2.0

    def __post_init__(self):
        if self.max_bytes < 1:
            raise ValueError("HTTP byte limit must be positive")
        if not isinstance(self.minimum_attempts, int) or not 1 <= self.minimum_attempts <= 10 or self.minimum_attempts > 1 and not self.retry_safe:
            raise ValueError('Additional attempts require an explicitly retry-safe operation')
        if not 1.0 <= self.retry_growth <= 4.0:
            raise ValueError('Retry growth must be between 1 and 4')


PAGE_OPERATION = OperationPolicy("page", 8 * 1024 * 1024)
CAPTCHA_OPERATION = OperationPolicy("captcha", 2 * 1024 * 1024)
DOWNLOAD_OPERATION = OperationPolicy("download", 128 * 1024 * 1024)
