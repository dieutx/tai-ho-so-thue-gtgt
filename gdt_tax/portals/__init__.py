"""Các nguồn dữ liệu trên cổng Dịch vụ công.

``build_portals`` là điểm duy nhất biết cách chọn lớp portal cho từng nguồn, nên
khi cổng thêm luồng mới chỉ cần bổ sung ở đây.
"""

from __future__ import annotations

from ..constants import SOURCE_DVC, SOURCE_ETAX
from .base import Portal
from .dvc import DvcPortal
from .etax import EtaxPortal

PORTAL_CLASSES = {
    SOURCE_ETAX: EtaxPortal,
    SOURCE_DVC: DvcPortal,
}


def build_portals(http, captcha, settings, csrf: str = "", logger=None) -> dict[str, Portal]:
    """Tạo sẵn portal cho mọi nguồn; chỉ nguồn ETAX cần ``csrf`` của trang hồ sơ."""
    portals: dict[str, Portal] = {}
    for source, portal_class in PORTAL_CLASSES.items():
        if portal_class is EtaxPortal:
            portals[source] = portal_class(http, captcha, settings, csrf=csrf, logger=logger)
        else:
            portals[source] = portal_class(http, captcha, settings, logger=logger)
    return portals


__all__ = ["PORTAL_CLASSES", "DvcPortal", "EtaxPortal", "Portal", "build_portals"]
