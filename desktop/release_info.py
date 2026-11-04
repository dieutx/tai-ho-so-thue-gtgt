"""User-initiated release lookup and startup update notification, separate from all tax HTTP sessions."""
from __future__ import annotations

import html
from dataclasses import dataclass
from urllib.parse import quote

import requests

from . import __version__

RELEASES_URL = "https://github.com/dieutx/tai-ho-so-thue-gtgt/releases"
RELEASES_API = "https://api.github.com/repos/dieutx/tai-ho-so-thue-gtgt/releases"


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    page_url: str
    download_url: str
    notes: str = ''
    published_at: str = ''


def latest_release(get=requests.get) -> ReleaseInfo | None:
    """Return the highest public release, or None when the public API is unavailable."""
    response = get(
        RELEASES_API,
        timeout=8,
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"TaiHoSoThue/{__version__}"},
    )
    if getattr(response, "status_code", 0) != 200:
        return None
    try:
        releases = response.json()
    except (ValueError, TypeError):
        return None
    return _select_release(releases)


def _select_release(releases) -> ReleaseInfo | None:
    from packaging.version import InvalidVersion, Version

    if not isinstance(releases, list):
        return None
    best: tuple[Version, ReleaseInfo] | None = None
    for item in releases:
        if not isinstance(item, dict) or item.get('draft') or item.get('prerelease'):
            continue
        tag = str(item.get("tag_name") or "").strip()
        version = tag.removeprefix("desktop-v").removeprefix("v")
        try:
            parsed = Version(version)
        except InvalidVersion:
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        links = item.get("assets", [])
        download = ""
        if isinstance(links, list):
            for link in links:
                if (isinstance(link, dict) and link.get("name") == "TaiHoSoThue-Windows.exe"
                        and link.get("browser_download_url")):
                    download = str(link["browser_download_url"])
                    break
        page = str(item.get("html_url") or "") or (
            f"{RELEASES_URL}/tag/{quote(tag, safe='')}"
        )
        if not download:
            download = page
        info = ReleaseInfo(str(parsed), tag, page, download,
                           str(item.get('body') or ''), str(item.get('published_at') or ''))
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
            return 'Trang phát hành đang riêng tư hoặc chưa có bản công khai. <a href="' + RELEASES_URL + '">Mở GitHub để xem bản tải</a>.'
        response.raise_for_status()
        releases = response.json()
        if not isinstance(releases, list) or not releases:
            return "Chưa có phiên bản phát hành công khai trên GitHub."
        latest = _select_release(releases)
        if latest is None:
            return "Chưa có phiên bản ổn định hợp lệ. Mở GitHub để xem chi tiết."
        tag = latest.tag[:80]
        from packaging.version import InvalidVersion, Version
        try:
            newer = Version(tag.removeprefix("desktop-v").removeprefix("v")) > Version(__version__)
        except InvalidVersion:
            return "Có thông tin phát hành nhưng chưa xác định được thứ tự phiên bản. Mở GitHub để xem chi tiết."
        if newer:
            url = html.escape(latest.page_url, quote=True)
            return f'Có bản mới: <b>{html.escape(tag)}</b>. <a href="{url}">Xem thay đổi và tải bản phát hành</a>.'
        return "Bản đang dùng đã bằng hoặc mới hơn bản phát hành công khai."
    except (requests.RequestException, ValueError, TypeError):
        return "Chưa kiểm tra được bản mới. Kiểm tra mạng hoặc mở trang phát hành trên GitHub."
