"""
Locates the Steam installation and reads its configuration files
(libraryfolders.vdf and loginusers.vdf), which use the Valve KeyValues
(VDF) format.
"""
from __future__ import annotations

import re
from pathlib import Path

DEFAULT_STEAM_PATH = Path("C:/Program Files (x86)/Steam")


def find_steam_path() -> Path | None:
    """
    Tries the default install path first; if it does not exist, falls back to
    the Windows registry (useful when Steam was installed elsewhere).
    """
    if DEFAULT_STEAM_PATH.exists():
        return DEFAULT_STEAM_PATH

    try:
        import winreg
    except ImportError:
        return None  # not running on Windows

    registry_lookups = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    )
    for hive, subkey, value_name in registry_lookups:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                path = Path(value)
                if path.exists():
                    return path
        except OSError:
            continue

    return None


def _parse_vdf(text: str) -> dict:
    """
    Simple (recursive) parser for the Valve KeyValues format.
    Enough for libraryfolders.vdf and loginusers.vdf, which do not use any
    advanced feature of the format (comments, conditionals, etc.).
    """
    # Each token records whether it is a block brace ({ or }) or a quoted
    # string -- this avoids confusing an empty string "" with the '{}' char.
    tokens = []
    for match in re.finditer(r'"((?:[^"\\]|\\.)*)"|([{}])', text):
        if match.group(1) is not None:
            tokens.append(("str", match.group(1)))
        else:
            tokens.append(("brace", match.group(2)))

    def unescape(value: str) -> str:
        return value.replace('\\"', '"').replace("\\\\", "\\")

    pos = 0

    def parse_object() -> dict:
        nonlocal pos
        obj: dict = {}
        while pos < len(tokens):
            kind, value = tokens[pos]
            if kind == "brace" and value == "}":
                pos += 1
                return obj
            key = unescape(value)
            pos += 1
            if pos >= len(tokens):
                break
            next_kind, next_value = tokens[pos]
            if next_kind == "brace" and next_value == "{":
                pos += 1
                obj[key] = parse_object()
            else:
                obj[key] = unescape(next_value)
                pos += 1
        return obj

    if not tokens:
        return {}

    # The first token is the root key (e.g. "libraryfolders" or "users");
    # step straight into its object.
    pos = 1
    if pos < len(tokens) and tokens[pos] == ("brace", "{"):
        pos += 1
        return parse_object()
    return {}


def _read_vdf(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return _parse_vdf(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def get_installed_appids(steam_path: Path) -> list[str]:
    """Returns every installed appid, across all libraries/drives."""
    data = _read_vdf(steam_path / "config" / "libraryfolders.vdf")
    appids: list[str] = []
    for entry in data.values():
        if isinstance(entry, dict):
            apps = entry.get("apps", {})
            if isinstance(apps, dict):
                for appid in apps.keys():
                    if appid not in appids:
                        appids.append(appid)
    return appids


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def get_local_users(steam_path: Path) -> list[dict]:
    """
    Returns one entry per account already logged in on this machine:
    {'steamid', 'account_name', 'persona_name', 'most_recent', 'timestamp'}.
    """
    data = _read_vdf(steam_path / "config" / "loginusers.vdf")
    users = []
    for steamid, info in data.items():
        if isinstance(info, dict):
            users.append(
                {
                    "steamid": steamid,
                    "account_name": info.get("AccountName", ""),
                    "persona_name": info.get("PersonaName", ""),
                    "most_recent": str(info.get("MostRecent", "0")) == "1",
                    "timestamp": _to_int(info.get("Timestamp", 0)),
                }
            )
    return users
