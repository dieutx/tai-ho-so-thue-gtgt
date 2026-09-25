"""Cho phép chạy gói bằng ``python -m gdt_tax``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
