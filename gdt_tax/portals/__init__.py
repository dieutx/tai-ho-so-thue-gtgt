"""Các nguồn dữ liệu trên cổng Dịch vụ công.

``build_portals`` là điểm duy nhất biết cách chọn lớp portal cho từng nguồn, nên
khi cổng thêm luồng mới chỉ cần bổ sung ở đây. Tài khoản cá nhân có bộ portal
riêng, không trộn với nguồn doanh nghiệp.
"""

from __future__ import annotations

from ..constants import (
    ACCOUNT_PERSONAL,
    SOURCE_CANHAN,
    SOURCE_DVC,
    SOURCE_DVC_PERSONAL,
    SOURCE_ETAX,
    SOURCE_ETAX_LEGACY,
)
from .base import Portal
from .dvc import DvcPortal
from .etax import EtaxPortal
from .etax_legacy import EtaxLegacyFallback, EtaxLegacyPortal
from .personal import CanhanNoticePortal, DvcPersonalPortal

PORTAL_CLASSES = {
    SOURCE_ETAX_LEGACY: EtaxLegacyPortal,
    SOURCE_ETAX: EtaxPortal,
    SOURCE_DVC: DvcPortal,
    SOURCE_DVC_PERSONAL: DvcPersonalPortal,
    SOURCE_CANHAN: CanhanNoticePortal,
}

PERSONAL_PORTAL_CLASSES = {
    SOURCE_DVC_PERSONAL: DvcPersonalPortal,
    SOURCE_CANHAN: CanhanNoticePortal,
}


def build_portals(http, captcha, settings, csrf: str = "", logger=None) -> dict[str, Portal]:
    """Chỉ tạo nguồn đang bật; đăng nhập legacy được trì hoãn tới lần tra cứu."""
    if settings.account_type == ACCOUNT_PERSONAL:
        return {
            source: portal_class(http, captcha, settings, csrf=csrf, logger=logger)
            if portal_class is CanhanNoticePortal
            else portal_class(http, captcha, settings, logger=logger)
            for source, portal_class in PERSONAL_PORTAL_CLASSES.items()
            if settings.source_enabled(source)
        }

    portals: dict[str, Portal] = {}
    for source, portal_class in PORTAL_CLASSES.items():
        if source not in (SOURCE_ETAX, SOURCE_DVC, SOURCE_ETAX_LEGACY):
            continue
        if not settings.source_enabled(source):
            continue
        if portal_class is EtaxPortal:
            portals[source] = portal_class(http, captcha, settings, csrf=csrf, logger=logger)
        else:
            portals[source] = portal_class(http, captcha, settings, logger=logger)

    return portals


__all__ = [
    "PERSONAL_PORTAL_CLASSES",
    "PORTAL_CLASSES",
    "CanhanNoticePortal",
    "DvcPersonalPortal",
    "DvcPortal",
    "EtaxLegacyFallback",
    "EtaxLegacyPortal",
    "EtaxPortal",
    "Portal",
    "build_portals",
]
