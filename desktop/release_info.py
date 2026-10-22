"""User-initiated release lookup and startup update notification, separate from all tax HTTP sessions."""
from __future__ import annotations

import html
from dataclasses import dataclass
from urllib.parse import quote

import requests

from . import __version__

RELEASES_URL = "https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/releases"
RELEASES_API = "https://gitlab.com/api/v4/projects/dieutx%2Ftai-ho-so-thue-gtgt/releases"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    page_url: str
    download_url: str


def latest_release(get=requests.get) -> ReleaseInfo | None:
    """Return the highest public release, or None when the public API is unavailable."""
    from packaging.version import InvalidVersion, Version

    response = get(
        RELEASES_API,
        timeout=8,
        headers={"Accept": "application/json", "User-Agent": f"TaiHoSoThue/{__version__}"},
    )
    if getattr(response, "status_code", 0) != 200:
        return None
    try:
        releases = response.json()
    except (ValueError, TypeError):
        return None
    if not isinstance(releases, list):
        return None
    best: tuple[Version, ReleaseInfo] | None = None
    for item in releases:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag_name") or "").strip()
        version = tag.removeprefix("desktop-v").removeprefix("v")
        try:
            parsed = Version(version)
        except InvalidVersion:
            continue
        links = item.get("assets", {}).get("links", [])
        download = ""
        if isinstance(links, list):
            for link in links:
                if (isinstance(link, dict) and link.get("name") == "TaiHoSoThue-Windows.exe"
                        and link.get("direct_asset_url")):
                    download = str(link["direct_asset_url"])
                    break
        page = str((item.get("_links") or {}).get("self") or "") or (
            f"{RELEASES_URL}/{quote(tag, safe='')}"
        )
        if not download:
            download = f"{RELEASES_URL}/{quote(tag, safe='')}/downloads/TaiHoSoThue-Windows.exe"
        info = ReleaseInfo(str(parsed), tag, page, download)
        if best is None or parsed > best[0]:
            best = (parsed, info)
    return best[1] if best else None


def auto_update_release(get=requests.get, current: str = __version__) -> ReleaseInfo | None:
    """Return a newer release; network/format failures are deliberately silent for startup."""
    from packaging.version import InvalidVersion, Version

    try:
        info = latest_release(get)
        if info is not None and Version(info.version) > Version(current):
            return info
    except (requests.RequestException, ValueError, TypeError, InvalidVersion):
        return None
    return None



def release_message(get=requests.get) -> str:
    try:
        response = get(RELEASES_API, timeout=12, headers={"Accept": "application/json"})
        if response.status_code in {401, 403, 404}:
            return 'Trang phát hành đang riêng tư hoặc chưa có bản công khai. <a href="' + RELEASES_URL + '">Mở GitLab để xem bản tải</a>.'
        response.raise_for_status()
        releases = response.json()
        if not isinstance(releases, list) or not releases:
            return "Chưa có phiên bản phát hành công khai trên GitLab."
        latest = releases[0]
        if not isinstance(latest, dict):
            return "Thông tin phát hành chưa đúng định dạng. Mở GitLab để xem chi tiết."
        tag = str(latest.get("tag_name", ""))[:80]
        from packaging.version import InvalidVersion, Version
        try:
            newer = Version(tag.removeprefix("desktop-v").removeprefix("v")) > Version(__version__)
        except InvalidVersion:
            return "Có thông tin phát hành nhưng chưa xác định được thứ tự phiên bản. Mở GitLab để xem chi tiết."
        if newer:
            url = RELEASES_URL + "/" + quote(tag, safe="")
            return f'Có bản mới: <b>{html.escape(tag)}</b>. <a href="{url}">Xem thay đổi và tải bản phát hành</a>.'
        return "Bản đang dùng đã bằng hoặc mới hơn bản phát hành công khai."
    except (requests.RequestException, ValueError, TypeError):
        return "Chưa kiểm tra được bản mới. Kiểm tra mạng hoặc mở trang phát hành trên GitLab."
