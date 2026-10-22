"""Qt background adapters for public release lookup."""
from __future__ import annotations

from threading import Thread

import requests
from PySide6.QtCore import QObject, Signal

from .release_info import RELEASES_API as RELEASES_API
from .release_info import RELEASES_URL as RELEASES_URL
from .release_info import ReleaseInfo as ReleaseInfo
from .release_info import auto_update_release as auto_update_release
from .release_info import latest_release as latest_release
from .release_info import release_message as release_message


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


class NewerReleaseChecker(QObject):
    """Background startup check; emits only when a release newer than the app exists."""

    found = Signal(object)

    def __init__(self, parent=None, get=requests.get) -> None:
        super().__init__(parent)
        self.get = get

    def start(self) -> None:
        def run():
            info = auto_update_release(self.get)
            if info is not None:
                try:
                    self.found.emit(info)
                except RuntimeError:
                    pass  # the owning window was closed while the GET was in flight
        Thread(target=run, name="release-check-startup", daemon=True).start()

