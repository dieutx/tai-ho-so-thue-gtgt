"""Exit policy shared by offline commands; outputs survive partial quality."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_INPUT_ERROR = 2


def quality_summary(stage: str, rows: list[dict], *, complete_status: str) -> dict:
    statuses = Counter(str(row.get("status", "UNKNOWN")) for row in rows)
    incomplete = sum(row.get("status") != complete_status or row.get("validation_status") == "PARTIAL" for row in rows)
    return {"schema_version": "quality-summary-v1", "stage": stage, "count": len(rows),
            "statuses": dict(statuses), "incomplete": incomplete,
            "exit_code": EXIT_INCOMPLETE if incomplete else EXIT_OK}


def write_summary(path: str | None, summary: dict) -> int:
    if path:
        from .export import _atomic_write
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"))
    return int(summary["exit_code"])
