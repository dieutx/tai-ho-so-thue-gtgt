"""Optional cooperation points for embedded clients; CLI defaults stay unchanged."""
from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event
from typing import Any


class RunCancelled(Exception):
    """Raised only at safe boundaries, never while committing a file."""


class RunHooks:
    def __init__(self, cancel: Event | None = None,
                 progress: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.cancel = cancel
        self.progress = progress

    def check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise RunCancelled("Đã dừng — còn dữ liệu chưa xử lý")

    def pause(self, seconds: float, sleep: Callable[[float], None] = time.sleep) -> None:
        self.check()
        if self.cancel is None:
            sleep(seconds)
        elif self.cancel.wait(max(0, seconds)):
            self.check()

    def emit(self, **payload: Any) -> None:
        if self.progress is not None:
            self.progress(payload)
