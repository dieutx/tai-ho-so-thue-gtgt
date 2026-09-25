"""Lớp chạy tương thích cho gói :mod:`gdt_tax`.

Script gốc đã được tách thành các module trong ``gdt_tax/``. File này chỉ giữ
lại lệnh chạy cũ để không phải đổi thói quen::

    python taitokhaiGTGT_fix_v12_full.py --from-date 01/01/2025 --to-date 31/01/2025

Cách chạy khuyến nghị là ``python -m gdt_tax`` (hoặc ``gdt-tax`` sau khi
``pip install -e .``). Xem ``docs/ARCHITECTURE.md`` để biết cấu trúc module.
"""

from __future__ import annotations

from gdt_tax.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
