"""Công cụ tải hồ sơ thuế GTGT từ Cổng Dịch vụ công của Cục Thuế.

Gói được chia theo module nhỏ, mỗi module một trách nhiệm:

``gdt_tax.config``
    Đọc cấu hình từ biến môi trường và file ``.env``.
``gdt_tax.dates``
    Quy tắc ngày tháng và chia khoảng tra cứu tối đa 31 ngày.
``gdt_tax.captcha``
    Các bộ nhận dạng CAPTCHA có thể thay thế (plugin).
``gdt_tax.portals``
    Cách tra cứu và tải riêng cho từng nguồn dữ liệu (DVC/ETAX).
``gdt_tax.pipeline``
    Ghép các giai đoạn thành luồng chạy hoàn chỉnh.

Gói này cố ý không import các thư viện nặng (``easyocr``, ``torch``) ở cấp
module. Chúng chỉ được nạp khi bộ nhận dạng CAPTCHA tương ứng thực sự được dùng.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
