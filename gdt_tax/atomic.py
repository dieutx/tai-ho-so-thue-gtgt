"""Bounded retries for transient Windows sharing/OneDrive rename locks."""
from __future__ import annotations

import os
import time
from pathlib import Path


def replace_with_retry(source: str | Path, target: str | Path) -> None:
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 4:
                raise
            time.sleep(0.15 * 2 ** attempt)
