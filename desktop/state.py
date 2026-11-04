"""Shared configuration, account-scoped paths and independent per-tab views."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from gdt_tax.identity import IdentityError, account_fingerprint
from gdt_tax.ownership import check_owner

from .services import JobResult

FOLDERS = {"tax": "to-khai", "gnt": "gnt", "notice": "thong-bao", "offline": "phan-tich"}


def job_output(base: Path, username: str, mode: str, account_type: str = "DN") -> Path:
    if mode == "offline":
        return base / FOLDERS[mode]
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", username)[:48].strip("_") or "tai-khoan"
    account = f"{safe}-{hashlib.sha256(username.encode()).hexdigest()[:8]}"
    # Tách hẳn kho cá nhân/doanh nghiệp; không di chuyển hay ghi đè dữ liệu cũ.
    root = base / "ca-nhan" if account_type == "CN" else base
    target = root / account / FOLDERS[mode]
    fresh = root / account / 'tai-moi' / FOLDERS[mode]
    key = account_fingerprint(username)
    # Preserve existing verified output; keep unowned legacy files untouched.
    # Once a new namespace is in use, keep using it even if old files are moved.
    if fresh.exists():
        check_owner(fresh, key)
        return fresh
    try:
        check_owner(target, key)
    except IdentityError as error:
        if not str(error).startswith('DIRECTORY_LEGACY_UNOWNED:'):
            raise
        return fresh
    return target


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
    cqt_filter: str = "all"
    type_filter: str = ""
    column_widths: dict[str, int] = field(default_factory=dict)
    conditions_collapsed: bool = False
    last_task: JobResult | None = None
    from_date: str = ""
    to_date: str = ""
    preset: str = "recent30"
