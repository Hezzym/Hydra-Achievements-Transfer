"""
Protection for the API key stored in config.json.

On Windows it uses DPAPI (CryptProtectData/CryptUnprotectData), which ties
the value to the current user of the machine. On other platforms it only
base64-encodes it (no real encryption), keeping the same interface.

Protected values carry the "dpapi:" prefix; values without it are treated
as plain text (compatibility with old configuration files).
"""
from __future__ import annotations

import base64
import sys

PREFIX = "dpapi:"


def is_protected(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def protect(text: str) -> str:
    if not text:
        return ""
    raw = text.encode("utf-8")
    protected = _dpapi_protect(raw) if _available() else raw
    return PREFIX + base64.b64encode(protected).decode("ascii")


def unprotect(value: str) -> str:
    if not value or not is_protected(value):
        # Legacy plain-text value (or empty): return it unchanged.
        return value or ""
    raw = base64.b64decode(value[len(PREFIX):])
    if _available():
        raw = _dpapi_unprotect(raw)
    return raw.decode("utf-8")


def _available() -> bool:
    return sys.platform == "win32"


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    def _make_blob(data: bytes):
        buffer = ctypes.create_string_buffer(bytes(data))
        blob = _DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        return blob, buffer

    def _blob_bytes(blob) -> bytes:
        data = ctypes.string_at(blob.pbData, blob.cbData)
        _kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))
        return data

    def _dpapi_protect(data: bytes) -> bytes:
        blob_in, _keep = _make_blob(data)
        blob_out = _DATA_BLOB()
        ok = _crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            raise OSError("CryptProtectData failed")
        return _blob_bytes(blob_out)

    def _dpapi_unprotect(data: bytes) -> bytes:
        blob_in, _keep = _make_blob(data)
        blob_out = _DATA_BLOB()
        ok = _crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            raise OSError("CryptUnprotectData failed")
        return _blob_bytes(blob_out)

else:
    def _dpapi_protect(data: bytes) -> bytes:
        return data

    def _dpapi_unprotect(data: bytes) -> bytes:
        return data
