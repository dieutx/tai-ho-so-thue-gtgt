"""Optional cooperation points for embedded clients; CLI defaults stay unchanged."""
from __future__ import annotations

import math
import os
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from threading import Event
from typing import Any

from .errors import ConfigError, NetworkError
from .metrics import HttpMetrics

#: Hạn mức mặc định của một lượt chạy (30 phút).
DEFAULT_MAX_SECONDS = 1800.0

#: Biến môi trường nới hạn mức cho lượt chạy dải ngày dài (ví dụ 2018 → nay).
BUDGET_SECONDS_ENV = "GDT_RUN_BUDGET_SECONDS"


def default_max_seconds(environ: Mapping[str, str] | None = None,
                        default: float = DEFAULT_MAX_SECONDS) -> float:
    """Hạn mức thời gian mặc định, có thể nới bằng ``GDT_RUN_BUDGET_SECONDS``.

    Một dải ngày dài (2018 → nay) cần hơn 30 phút, trong khi hạn mức mặc định giữ
    nguyên cho lượt chạy thường. Chỉ biến môi trường mới nới được; các nơi truyền
    ``RunBudget(max_seconds=...)`` tường minh không bị ảnh hưởng.
    """
    values = os.environ if environ is None else environ
    raw = str(values.get(BUDGET_SECONDS_ENV, "")).strip()
    if not raw:
        return default
    try:
        seconds = float(raw)
    except ValueError as error:
        raise ConfigError(f"{BUDGET_SECONDS_ENV} phải là số giây, nhận được {raw!r}") from error
    if not math.isfinite(seconds) or seconds <= 0:
        raise ConfigError(f"{BUDGET_SECONDS_ENV} phải là số dương hữu hạn, nhận được {raw!r}")
    return seconds


class RunCancelled(Exception):
    """Raised only at safe boundaries, never while committing a file."""


@dataclass
class RunBudget:
    """Shared limits include retries and redirects, using a monotonic clock."""

    max_seconds: float = field(default_factory=default_max_seconds)
    max_requests: int = 10_000
    max_bytes: int = 1024 * 1024 * 1024
    max_pages: int = 10_000
    max_auth_attempts: int = 20
    clock: Callable[[], float] = time.monotonic
    requests: int = 0
    bytes_read: int = 0
    pages: int = 0
    auth_attempts: int = 0
    max_records: int | None = None
    records: int = 0
    stop_on_http_errors: bool = False
    min_request_interval: float = 0
    last_request_at: float | None = field(default=None, init=False)
    started: float = field(init=False)

    def __post_init__(self):
        if not math.isfinite(self.max_seconds) or min(self.max_seconds, self.max_requests, self.max_bytes, self.max_pages, self.max_auth_attempts) <= 0:
            raise ValueError("Run budget must be positive and finite")
        self.started = self.clock()

    def remaining(self) -> float:
        remaining = self.max_seconds - (self.clock() - self.started)
        if remaining <= 0:
            raise NetworkError("RUN_BUDGET_EXCEEDED: deadline")
        return remaining

    def request(self):
        self.remaining()
        if self.min_request_interval and self.last_request_at is not None:
            time.sleep(max(0, self.min_request_interval - (self.clock() - self.last_request_at)))
        if self.requests >= self.max_requests:
            raise NetworkError("RUN_BUDGET_EXCEEDED: requests")
        self.requests += 1
        self.last_request_at = self.clock()

    def record(self):
        if self.max_records is not None and self.records >= self.max_records:
            raise RunCancelled('Đã đạt giới hạn hồ sơ cho phép của lượt kiểm thử')
        self.records += 1

    def consume(self, count: int):
        self.remaining()
        self.bytes_read += count
        if self.bytes_read > self.max_bytes:
            raise NetworkError("RUN_BUDGET_EXCEEDED: bytes")

    def page(self):
        self.remaining()
        if self.pages >= self.max_pages:
            raise NetworkError("RUN_BUDGET_EXCEEDED: pages")
        self.pages += 1

    def authenticate(self):
        self.remaining()
        if self.auth_attempts >= self.max_auth_attempts:
            raise NetworkError("RUN_BUDGET_EXCEEDED: authentication attempts")
        self.auth_attempts += 1


class RunHooks:
    def __init__(self, cancel: Event | None = None,
                 progress: Callable[[dict[str, Any]], None] | None = None,
                 budget: RunBudget | None = None,
                 support: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.cancel = cancel
        self.progress = progress
        self.budget = budget
        self.support = support
        self.run_id = uuid.uuid4().hex
        self.catalog_checkpoint: Callable[[dict[str, Any]], None] | None = None
        self.http_metrics = HttpMetrics()

    def check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise RunCancelled("Đã dừng — còn dữ liệu chưa xử lý")
        if self.budget is not None:
            self.budget.remaining()

    def pause(self, seconds: float, sleep: Callable[[float], None] = time.sleep) -> None:
        self.check()
        if self.budget is not None and seconds >= self.budget.remaining():
            raise NetworkError("RUN_BUDGET_EXCEEDED: retry delay")
        if self.cancel is None:
            sleep(seconds)
        elif self.cancel.wait(max(0, seconds)):
            self.check()

    def emit(self, **payload: Any) -> None:
        if self.progress is not None:
            self.progress(payload)

    def emit_support(self, payload: dict[str, Any]) -> None:
        if self.support is not None:
            self.support(payload)
