"""Synthetic accounts only; regular tests never read the user's vault."""
from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from desktop.account_store import AccountStore, AccountStoreError, target_name

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAS_QT = importlib.util.find_spec('PySide6') is not None


class AccountStoreTests(unittest.TestCase):
    def test_namespace_is_fixed_and_invalid_credentials_never_reach_native_api(self):
        self.assertTrue(target_name('synthetic').startswith('TaiHoSoThue/ETAX/v1/'))
        self.assertNotIn('synthetic', target_name('synthetic'))
        self.assertNotEqual(target_name('company-a'), target_name('company-b'))
        store = AccountStore()
        with patch.object(store, '_vault', side_effect=AssertionError('native API reached')):
            for username, password in (('', 'secret'), ('a\0b', 'secret'), ('a', ''), ('a', 'x' * 1281)):
                with self.assertRaises(AccountStoreError):
                    store.save(username, password)

    def test_non_windows_has_no_file_fallback(self):
        with patch('desktop.account_store.os.name', 'posix'):
            with self.assertRaises(AccountStoreError):
                AccountStore().accounts()


@unittest.skipUnless(HAS_QT, 'Qt optional')
class SavedAccountUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widgets = []

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication, QEvent
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def store(self):
        store = Mock()
        store.accounts.return_value = ['company-a', 'company-b']
        store.password.side_effect = lambda name: {'company-a': 'secret-a', 'company-b': 'secret-b'}.get(name)
        return store

    def test_select_switch_new_account_and_forget_clear_stale_passwords(self):
        from PySide6.QtWidgets import QLineEdit

        from desktop.account_dialog import AccountDialog
        store = self.store()
        dialog = AccountDialog(username='company-a', store=store)
        self.widgets.append(dialog)
        self.assertEqual(dialog.password.text(), 'secret-a')
        dialog.accounts.setCurrentText('company-b')
        self.assertEqual(dialog.password.text(), 'secret-b')
        self.assertEqual(dialog.password.echoMode(), QLineEdit.EchoMode.Password)
        dialog.accounts.setEditText('company-new')
        self.assertEqual(dialog.password.text(), '')
        dialog.accounts.setCurrentText('company-a')
        dialog.forget_account()
        store.forget.assert_called_once_with('company-a')
        self.assertEqual(dialog.accounts.findText('company-a'), -1)
        self.assertEqual(dialog.password.text(), '')
        dialog.reject()
        self.assertIsNone(dialog.take_credentials())
        store.save.assert_not_called()

    def test_vault_unavailable_still_allows_session_login(self):
        from desktop.account_dialog import AccountDialog
        store = self.store()
        store.accounts.side_effect = AccountStoreError('vault unavailable')
        dialog = AccountDialog(username='new-company', password='session-secret', store=store)
        self.widgets.append(dialog)
        self.assertFalse(dialog.remember.isChecked())
        dialog.accept_if_valid()
        self.assertEqual(dialog.take_credentials(), ('new-company', 'session-secret'))
        self.assertEqual(dialog.password.text(), '')
        store.save.assert_not_called()

    def test_save_only_successful_login_when_requested_and_mst_click_opens_menu(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        from desktop.services import JobResult, RunConfig
        from desktop.settings_store import SettingsStore
        from desktop.ui import MainWindow
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            window = MainWindow(SettingsStore(root / 'settings.json'))
            self.widgets.append(window)
            window.account_store = self.store()
            try:
                for state, remember, expected in (('ERROR', True, 0), ('SUCCESS', False, 0), ('SUCCESS', True, 1)):
                    window.account_store.save.reset_mock()
                    window.active_config = RunConfig('login', root, username='company-a', password='secret-a')
                    window.remember_login = remember
                    with patch.object(window, 'error'):
                        window.on_completed(JobResult(state, 'synthetic', root))
                    self.assertEqual(window.account_store.save.call_count, expected)
                    self.assertFalse(window.remember_login)
                with patch.object(window, 'saved_accounts_menu') as menu:
                    QTest.mouseClick(window.account_label, Qt.MouseButton.LeftButton)
                menu.assert_called_once()
                if window.store.path.exists():
                    self.assertNotIn('secret-a', window.store.path.read_text())
            finally:
                window.close()
