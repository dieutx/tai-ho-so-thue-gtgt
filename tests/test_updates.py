"""Offline tests for startup update checks and the visible update banner."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

try:
    from PySide6.QtWidgets import QApplication
    HAS_QT = True
except ImportError:  # pragma: no cover - core-only install
    HAS_QT = False


def release_payload(tag: str, version_url: str = "") -> dict:
    links = []
    if version_url:
        links.append({"name": "TaiHoSoThue-Windows.exe", "direct_asset_url": version_url})
    return {
        "tag_name": tag,
        "assets": {"links": links},
        "_links": {"self": "https://example.test/releases/" + tag},
    }


class ReleaseLookupTests(unittest.TestCase):
    def test_latest_release_picks_highest_semantic_version_and_asset(self):
        from desktop.updates import latest_release
        response = Mock(status_code=200)
        response.json.return_value = [
            release_payload("desktop-v2.0.1", "https://example.test/2.0.1.exe"),
            release_payload("desktop-v2.0.2", "https://example.test/2.0.2.exe"),
            release_payload("not-a-version"),
        ]
        info = latest_release(Mock(return_value=response))
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "2.0.2")
        self.assertEqual(info.download_url, "https://example.test/2.0.2.exe")

    def test_latest_release_falls_back_to_release_download_url(self):
        from desktop.updates import latest_release
        response = Mock(status_code=200)
        response.json.return_value = [release_payload("desktop-v2.0.2")]
        info = latest_release(Mock(return_value=response))
        self.assertIsNotNone(info)
        self.assertTrue(info.download_url.endswith("/desktop-v2.0.2/downloads/TaiHoSoThue-Windows.exe"))

    def test_auto_update_only_returns_newer_release(self):
        from desktop.updates import auto_update_release
        newer = Mock(status_code=200)
        newer.json.return_value = [release_payload("desktop-v2.0.2", "https://example.test/2.0.2.exe")]
        self.assertEqual(auto_update_release(Mock(return_value=newer), current="2.0.1").version, "2.0.2")
        same = Mock(status_code=200)
        same.json.return_value = [release_payload("desktop-v2.0.1")]
        self.assertIsNone(auto_update_release(Mock(return_value=same), current="2.0.1"))

    def test_auto_update_is_silent_when_network_or_payload_fails(self):
        from desktop.updates import auto_update_release
        self.assertIsNone(auto_update_release(Mock(side_effect=requests.RequestException("offline"))))
        bad = Mock(status_code=200)
        bad.json.return_value = {"unexpected": "shape"}
        self.assertIsNone(auto_update_release(Mock(return_value=bad)))


@unittest.skipUnless(HAS_QT, "Desktop Qt dependencies are optional")
class UpdateBannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from desktop.settings_store import SettingsStore
        from desktop.ui import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.store = SettingsStore(Path(self.temp.name) / "settings.json")
        self.window = MainWindow(self.store)

    def tearDown(self):
        self.window.close()
        self.temp.cleanup()

    def test_banner_is_visible_and_dismissal_persists(self):
        from desktop.updates import ReleaseInfo
        info = ReleaseInfo(
            "9.9.9", "desktop-v9.9.9", "https://example.test/release/9.9.9",
            "https://example.test/9.9.9.exe",
        )
        self.window.show_update_banner(info)
        self.assertFalse(self.window.update_banner.isHidden())
        self.assertIn("9.9.9", self.window.update_text.text())
        self.window.dismiss_update()
        self.assertTrue(self.window.update_banner.isHidden())
        self.assertEqual(self.store.load().dismissed_update_version, "9.9.9")

    def test_dismissed_version_is_not_shown_again(self):
        from desktop.updates import ReleaseInfo
        self.window.preferences.dismissed_update_version = "9.9.9"
        self.window.show_update_banner(ReleaseInfo(
            "9.9.9", "desktop-v9.9.9", "https://example.test/release/9.9.9",
            "https://example.test/9.9.9.exe",
        ))
        self.assertTrue(self.window.update_banner.isHidden())


if __name__ == "__main__":
    unittest.main()
