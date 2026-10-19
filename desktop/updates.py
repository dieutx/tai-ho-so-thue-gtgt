"""User-initiated release lookup, separate from all tax HTTP sessions."""
from __future__ import annotations

import html
from threading import Thread
from urllib.parse import quote

import requests
from PySide6.QtCore import QObject, Signal

from . import __version__

RELEASES_URL = "https://gitlab.com/dieutx/tai-ho-so-thue-gtgt/-/releases"
RELEASES_API = "https://gitlab.com/api/v4/projects/dieutx%2Ftai-ho-so-thue-gtgt/releases"


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


class UpdateChecker(QObject):
    done = Signal(str)

    def start(self) -> None:
        def run():
            message = release_message()
            try:
                self.done.emit(message)
            except RuntimeError:
                pass  # the owning window was closed while the GET was in flight
        Thread(target=run, name="release-check", daemon=True).start()
