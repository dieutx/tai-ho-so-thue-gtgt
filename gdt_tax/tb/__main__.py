"""Cho phép chạy ``python -m gdt_tax.tb``."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
