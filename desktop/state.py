"""Shared configuration, account-scoped paths and independent per-tab views."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from .services import JobResult

FOLDERS = {"tax": "to-khai", "gnt": "gnt", "notice": "thong-bao", "offline": "phan-tich"}


def job_output(base: Path, username: str, mode: str) -> Path:
    if mode == "offline":
        return base / FOLDERS[mode]
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", username)[:48].strip("_") or "tai-khoan"
    account = f"{safe}-{hashlib.sha256(username.encode()).hexdigest()[:8]}"
    return base / account / FOLDERS[mode]


@dataclass
class TabState:
    result: JobResult | None = None
    filter_text: str = ""
    scroll: int = 0
    horizontal_scroll: int = 0
    sort_column: int = -1
    sort_descending: bool = True
    message: str = "Sẵn sàng"
    rows: list[dict] = field(default_factory=list)
    status_filter: str = "all"
    conditions_collapsed: bool = False
    last_task: JobResult | None = None
