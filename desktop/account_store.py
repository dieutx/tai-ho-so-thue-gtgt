"""App-scoped generic credentials in the current user's Windows vault."""
from __future__ import annotations

import ctypes
import hashlib
import os
from ctypes import wintypes

PREFIX = 'TaiHoSoThue/ETAX/v1/'


class AccountStoreError(Exception):
    pass


def target_name(username: str, account_type: str = 'DN') -> str:
    """Namespace riêng cho cá nhân; giữ nguyên khóa cũ của doanh nghiệp."""
    digest = hashlib.sha256(username.encode('utf-8')).hexdigest()
    return PREFIX + ('CN/' + digest if account_type == 'CN' else digest)


class _Credential(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
                ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
                ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
                ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)), ('Persist', wintypes.DWORD),
                ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]


class AccountStore:
    """Never falls back to plaintext files; enumerate only our own namespace."""

    def __init__(self) -> None:
        self._api = None

    def _vault(self):
        if os.name != 'nt':
            raise AccountStoreError('Lưu mật khẩu chỉ hỗ trợ Windows Credential Manager.')
        if self._api is None:
            api = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
            pointer = ctypes.POINTER(_Credential)
            api.CredWriteW.argtypes = [pointer, wintypes.DWORD]
            api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
            api.CredEnumerateW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.POINTER(pointer))]
            api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
            for function in (api.CredWriteW, api.CredReadW, api.CredEnumerateW, api.CredDeleteW):
                function.restype = wintypes.BOOL
            api.CredFree.argtypes = [ctypes.c_void_p]
            api.CredFree.restype = None
            self._api = api
        return self._api

    @staticmethod
    def _failed() -> None:
        raise AccountStoreError('Không truy cập được Windows Credential Manager; có thể đăng nhập bằng cách nhập mật khẩu.')

    def accounts(self, account_type: str = 'DN') -> list[str]:
        api = self._vault()
        count = wintypes.DWORD()
        entries = ctypes.POINTER(ctypes.POINTER(_Credential))()
        if not api.CredEnumerateW(PREFIX + ('CN/*' if account_type == 'CN' else '*'), 0,
                                  ctypes.byref(count), ctypes.byref(entries)):
            if ctypes.get_last_error() == 1168:
                return []
            self._failed()
        try:
            names = set()
            for index in range(count.value):
                item = entries[index].contents
                username = item.UserName or ''
                if item.Type == 1 and username and item.TargetName == target_name(username, account_type):
                    names.add(username)
            return sorted(names, key=str.casefold)
        finally:
            api.CredFree(entries)

    def password(self, username: str, account_type: str = 'DN') -> str | None:
        api = self._vault()
        entry = ctypes.POINTER(_Credential)()
        if not api.CredReadW(target_name(username, account_type), 1, 0, ctypes.byref(entry)):
            if ctypes.get_last_error() == 1168:
                return None
            self._failed()
        try:
            item = entry.contents
            if item.UserName != username or item.CredentialBlobSize > 2560 or item.CredentialBlobSize % 2:
                self._failed()
            try:
                return ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize).decode('utf-16-le')
            except UnicodeError:
                self._failed()
        finally:
            api.CredFree(entry)

    def save(self, username: str, password: str, account_type: str = 'DN') -> None:
        if not username.strip() or '\0' in username or not password:
            raise AccountStoreError('Tài khoản hoặc mật khẩu trống/không hợp lệ.')
        encoded = password.encode('utf-16-le')
        if len(encoded) > 2560:
            raise AccountStoreError('Mật khẩu vượt giới hạn lưu của Windows Credential Manager.')
        api = self._vault()
        blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        entry = _Credential(Type=1, TargetName=target_name(username, account_type), UserName=username,
                            CredentialBlobSize=len(encoded), CredentialBlob=blob, Persist=2)
        try:
            if not api.CredWriteW(ctypes.byref(entry), 0):
                self._failed()
        finally:
            ctypes.memset(blob, 0, len(encoded))

    def forget(self, username: str, account_type: str = 'DN') -> None:
        api = self._vault()
        if not api.CredDeleteW(target_name(username, account_type), 1, 0) and ctypes.get_last_error() != 1168:
            self._failed()
