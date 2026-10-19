"""Windows-only API credential, separate from Git's existing OAuth login."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

TARGET = 'TaiHoSoThue:GitLabReleaseApi:gitlab.com'


class Credential(ctypes.Structure):
    _fields_ = [
        ('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
        ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
        ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
        ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
        ('Persist', wintypes.DWORD), ('AttributeCount', wintypes.DWORD),
        ('Attributes', ctypes.c_void_p), ('TargetAlias', wintypes.LPWSTR),
        ('UserName', wintypes.LPWSTR),
    ]


def read_token() -> str | None:
    if not hasattr(ctypes, 'WinDLL'):
        return None
    library = ctypes.WinDLL('Advapi32', use_last_error=True)
    library.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
    library.CredReadW.restype = wintypes.BOOL
    library.CredFree.argtypes = [ctypes.c_void_p]
    pointer = ctypes.POINTER(Credential)()
    if not library.CredReadW(TARGET, 1, 0, ctypes.byref(pointer)):
        return None
    try:
        return ctypes.string_at(pointer.contents.CredentialBlob, pointer.contents.CredentialBlobSize).decode('utf-8')
    finally:
        library.CredFree(pointer)


def save_token(token: str) -> None:
    library = ctypes.WinDLL('Advapi32', use_last_error=True)
    library.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    library.CredWriteW.restype = wintypes.BOOL
    data = token.encode('utf-8')
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    credential = Credential()
    credential.Type = 1
    credential.TargetName = TARGET
    credential.Comment = 'GitLab API token for authorized Tai Ho So Thue releases'
    credential.CredentialBlobSize = len(data)
    credential.CredentialBlob = buffer
    credential.Persist = 2
    credential.UserName = 'GitLabReleaseApi'
    if not library.CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if read_token() != token:
        raise RuntimeError('Credential persistence verification failed')
