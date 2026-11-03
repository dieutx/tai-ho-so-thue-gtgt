"""Các nguồn dữ liệu trên cổng Dịch vụ công.

``build_portals`` là điểm duy nhất biết cách chọn lớp portal cho từng nguồn, nên
khi cổng thêm luồng mới chỉ cần bổ sung ở đây.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..constants import SOURCE_DVC, SOURCE_ETAX, SOURCE_ETAX_LEGACY
from .base import Portal
from .dvc import DvcPortal
from .etax import EtaxPortal
from .etax_legacy import EtaxLegacyFallback, EtaxLegacyPortal

if TYPE_CHECKING:
    from .canhan import CanhanPortal

PORTAL_CLASSES = {
    SOURCE_ETAX_LEGACY: EtaxLegacyPortal,
    SOURCE_ETAX: EtaxPortal,
    SOURCE_DVC: DvcPortal,
}


def build_portals(http, captcha, settings, csrf: str = "", logger=None) -> dict[str, Portal | CanhanPortal]:
    """Chỉ tạo nguồn đang bật; đăng nhập legacy được trì hoãn tới lần tra cứu.

    Tài khoản cá nhân dùng phiên DSE riêng của ``canhan.gdt.gov.vn``, không mượn
    endpoint/cookie của doanh nghiệp hay DVC.
    """
    if getattr(settings, "account_type", "DN") == "CN":
        from .canhan import CanhanPortal  # tránh vòng import với gói tb
        return {SOURCE_ETAX_LEGACY: CanhanPortal(http, captcha, settings, logger)}
    portals: dict[str, Portal | CanhanPortal] = {}
    for source, portal_class in PORTAL_CLASSES.items():
        if not settings.source_enabled(source):
            continue
        if portal_class is EtaxPortal:
            portals[source] = portal_class(http, captcha, settings, csrf=csrf, logger=logger)
        else:
            portals[source] = portal_class(http, captcha, settings, logger=logger)

    return portals


__all__ = [
    "PORTAL_CLASSES",
    "DvcPortal",
    "EtaxLegacyFallback",
    "EtaxLegacyPortal",
    "EtaxPortal",
    "Portal",
    "build_portals",
]
