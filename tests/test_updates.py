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
        links.append({"name": "TaiHoSoThue-Windows.exe", "browser_download_url": version_url})
    return {
        "tag_name": tag,
        "assets": links,
        "html_url": "https://example.test/releases/" + tag,
    }


class ReleaseLookupTests(unittest.TestCase):
    def test_latest_release_picks_highest_semantic_version_and_asset(self):
        from desktop.release_info import latest_release
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

    def test_latest_release_without_exe_opens_the_release_page(self):
        from desktop.release_info import latest_release
        response = Mock(status_code=200)
        response.json.return_value = [release_payload("desktop-v2.0.2")]
        info = latest_release(Mock(return_value=response))
        self.assertIsNotNone(info)
        self.assertEqual(info.download_url, info.page_url)

    def test_release_includes_change_notes_and_publication_time(self):
        from desktop.release_info import latest_release
        response = Mock(status_code=200)
        response.json.return_value = [{**release_payload('desktop-v9.9.9'),
                                       'body': '- Cập nhật trạng thái CQT',
                                       'published_at': '2026-11-04T01:00:00Z'}]
        info = latest_release(Mock(return_value=response))
        self.assertEqual(info.notes, '- Cập nhật trạng thái CQT')
        self.assertEqual(info.published_at, '2026-11-04T01:00:00Z')

    def test_github_request_and_stable_release_filter(self):
        from desktop.release_info import RELEASES_API, latest_release, release_message

        response = Mock(status_code=200)
        response.json.return_value = [
            {**release_payload('desktop-v999.0.0'), 'draft': True},
            {**release_payload('desktop-v998.0.0'), 'prerelease': True},
            release_payload('desktop-v997.0.0rc1'),
            release_payload('desktop-v9.0.0', 'https://example.test/9.exe'),
            release_payload('desktop-v3.0.0'),
        ]
        get = Mock(return_value=response)
        info = latest_release(get)
        self.assertEqual(info.version, '9.0.0')
        self.assertEqual(get.call_args.args[0], RELEASES_API)
        self.assertTrue(RELEASES_API.startswith('https://api.github.com/repos/'))
        self.assertIn('desktop-v9.0.0', release_message(get))
        self.assertNotIn('999.0.0', release_message(get))

    def test_auto_update_only_returns_newer_release(self):
        from desktop.release_info import auto_update_release
        newer = Mock(status_code=200)
        newer.json.return_value = [release_payload("desktop-v2.0.2", "https://example.test/2.0.2.exe")]
        self.assertEqual(auto_update_release(Mock(return_value=newer), current="2.0.1").version, "2.0.2")
        same = Mock(status_code=200)
        same.json.return_value = [release_payload("desktop-v2.0.1")]
        self.assertIsNone(auto_update_release(Mock(return_value=same), current="2.0.1"))

    def test_auto_update_is_silent_when_network_or_payload_fails(self):
        from desktop.release_info import auto_update_release
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
        from desktop.release_info import ReleaseInfo
        info = ReleaseInfo(
            "9.9.9", "desktop-v9.9.9", "https://example.test/release/9.9.9",
            "https://example.test/9.9.9.exe",
        )
        self.window.show_update_banner(info)
        self.assertFalse(self.window.update_banner.isHidden())
        self.assertIn("9.9.9", self.window.update_text.text())
        self.assertTrue(self.window._update_dialog.isVisible())
        self.window.dismiss_update()
        self.assertTrue(self.window.update_banner.isHidden())
        self.assertEqual(self.store.load().dismissed_update_version, "9.9.9")

    def test_dismissed_version_is_not_shown_again(self):
        from desktop.release_info import ReleaseInfo
        self.window.preferences.dismissed_update_version = "9.9.9"
        self.window.show_update_banner(ReleaseInfo(
            "9.9.9", "desktop-v9.9.9", "https://example.test/release/9.9.9",
            "https://example.test/9.9.9.exe",
        ))
        self.assertTrue(self.window.update_banner.isHidden())

    def test_automatic_dialog_shows_notes_time_and_download_or_skip(self):
        from PySide6.QtWidgets import QPushButton, QTextBrowser

        from desktop.release_info import ReleaseInfo
        self.window.show_update_banner(ReleaseInfo('9.9.9', 'desktop-v9.9.9',
            'https://example.test/release', 'https://example.test/app.exe',
            '- Sửa trạng thái CQT\n- Tải theo mã hồ sơ', '2026-11-04T01:00:00Z'))
        dialog = self.window._update_dialog
        content = dialog.findChild(QTextBrowser).toPlainText()
        self.assertIn('Sửa trạng thái CQT', content)
        self.assertIn('04/11/2026', content)
        self.assertEqual({b.text() for b in dialog.findChildren(QPushButton)},
                         {'Tải bản cập nhật', 'Bỏ qua'})


if __name__ == "__main__":
    unittest.main()
