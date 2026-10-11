"""Cho phép chạy ``python -m gdt_tax.gnt``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
