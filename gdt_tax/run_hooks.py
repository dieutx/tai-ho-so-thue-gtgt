"""Optional cooperation points for embedded clients; CLI defaults stay unchanged."""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event
from typing import Any

from .errors import NetworkError


class RunCancelled(Exception):
    """Raised only at safe boundaries, never while committing a file."""


@dataclass
class RunBudget:
    """Shared limits include retries and redirects, using a monotonic clock."""

    max_seconds: float = 1800
    max_requests: int = 10_000
    max_bytes: int = 1024 * 1024 * 1024
    max_pages: int = 10_000
    max_auth_attempts: int = 20
    clock: Callable[[], float] = time.monotonic
    requests: int = 0
    bytes_read: int = 0
    pages: int = 0
    auth_attempts: int = 0
    started: float = field(init=False)

    def __post_init__(self):
        import math
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
        if self.requests >= self.max_requests:
            raise NetworkError("RUN_BUDGET_EXCEEDED: requests")
        self.requests += 1

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
