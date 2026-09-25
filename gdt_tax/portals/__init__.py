"""Các nguồn dữ liệu trên cổng Dịch vụ công.

``build_portals`` là điểm duy nhất biết cách chọn lớp portal cho từng nguồn, nên
khi cổng thêm luồng mới chỉ cần bổ sung ở đây.
"""

from __future__ import annotations

from ..constants import SOURCE_DVC, SOURCE_ETAX
from .base import Portal
from .dvc import DvcPortal
from .etax import EtaxPortal
from .etax_legacy import EtaxLegacyFallback, EtaxLegacyPortal

PORTAL_CLASSES = {
    SOURCE_ETAX: EtaxPortal,
    SOURCE_DVC: DvcPortal,
}


def build_portals(http, captcha, settings, csrf: str = "", logger=None) -> dict[str, Portal]:
    """Tạo sẵn portal cho mọi nguồn; chỉ nguồn ETAX cần ``csrf`` của trang hồ sơ.

    Khi ``settings.legacy_etax`` bật, portal ETAX (nguồn phục vụ các đoạn ngày
    trước mốc) được bọc bởi :class:`EtaxLegacyFallback`: đoạn nào cổng không trả
    hồ sơ sẽ được tra cứu thêm trên trang Thuế điện tử cũ.
    """
    portals: dict[str, Portal] = {}
    for source, portal_class in PORTAL_CLASSES.items():
        if portal_class is EtaxPortal:
            portals[source] = portal_class(http, captcha, settings, csrf=csrf, logger=logger)
        else:
            portals[source] = portal_class(http, captcha, settings, logger=logger)

    if settings.legacy_etax and SOURCE_ETAX in portals:
        legacy = EtaxLegacyPortal(http, captcha, settings, logger=logger)
        portals[SOURCE_ETAX] = EtaxLegacyFallback(portals[SOURCE_ETAX], legacy, logger=logger)
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
