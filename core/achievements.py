"""
Conversion from the Steam API JSON to the format used by GSE Saves, plus
safe writing of the achievements.json file (with rotating backups).

Optionally creates a "<appid>.<game_name>.txt" file inside the game folder
to help identify which game each numeric GSE Saves folder belongs to.
"""
from __future__ import annotations

import json
import os
import random
import re
import unicodedata
from pathlib import Path

MAX_BACKUPS = 5
ACHIEVEMENTS_FILENAME = "achievements.json"


def convert_to_gse_format(playerstats: dict) -> dict:
    """
    Takes the (already validated) 'playerstats' dictionary and converts the
    'achievements' list to the GSE Saves format:

        {"API_NAME": {"earned": bool, "earned_time": int}, ...}
    """
    converted: dict[str, dict] = {}
    for entry in playerstats.get("achievements", []):
        api_name = entry.get("apiname")
        if not api_name:
            continue
        converted[api_name] = {
            "earned": bool(entry.get("achieved", 0)),
            "earned_time": int(entry.get("unlocktime", 0)),
        }
    return converted


def read_achievements_file(appid: str) -> dict | None:
    """
    Reads <GSE Saves>/<appid>/achievements.json.
    Returns the parsed dict, or None if it does not exist / is unreadable.
    """
    path = get_appid_dir(appid) / ACHIEVEMENTS_FILENAME
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def diff_achievements(old: dict | None, new: dict) -> tuple[list[str], list[str]]:
    """
    Compares the current file with what is about to be written.

    Returns (gained, lost):
    - gained: achievements that become earned.
    - lost: achievements that were earned and stop being earned.
    """
    old = old or {}
    gained = [
        name
        for name, data in new.items()
        if data.get("earned") and not old.get(name, {}).get("earned", False)
    ]
    lost = [
        name
        for name, data in old.items()
        if data.get("earned") and not new.get(name, {}).get("earned", False)
    ]
    return gained, lost


def get_gse_saves_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if not appdata:
        raise RuntimeError("Could not find the %APPDATA% environment variable.")
    return Path(appdata) / "GSE Saves"


def get_appid_dir(appid: str) -> Path:
    return get_gse_saves_dir() / str(appid)


def _rotate_backups(target_dir: Path) -> None:
    """Keeps only the MAX_BACKUPS most recent achievements.json backups."""
    backups = sorted(
        target_dir.glob(f"{ACHIEVEMENTS_FILENAME}.*.bak"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old_backup in backups[MAX_BACKUPS:]:
        try:
            old_backup.unlink()
        except OSError:
            pass


def write_achievements_file(appid: str, achievements_data: dict) -> Path:
    """
    Writes achievements_data to <GSE Saves>/<appid>/achievements.json.

    Creates the required folders if missing. If a file already exists, it is
    backed up as achievements.json.<random_number>.bak before being
    overwritten, keeping only the MAX_BACKUPS most recent backups.
    """
    target_dir = get_appid_dir(appid)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = target_dir / ACHIEVEMENTS_FILENAME

    if target_file.exists():
        backup_suffix = random.randint(1000, 9999)
        backup_file = target_dir / f"{ACHIEVEMENTS_FILENAME}.{backup_suffix}.bak"
        while backup_file.exists():
            backup_suffix = random.randint(1000, 9999)
            backup_file = target_dir / f"{ACHIEVEMENTS_FILENAME}.{backup_suffix}.bak"
        target_file.replace(backup_file)
        _rotate_backups(target_dir)

    # Atomic write: write to .tmp and only then replace the final file, so a
    # failure midway never leaves achievements.json corrupted.
    tmp_file = target_dir / f"{ACHIEVEMENTS_FILENAME}.tmp"
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(achievements_data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_file, target_file)

    return target_file


def sanitize_game_name(game_name: str) -> str:
    """
    Makes the game name safe for use in a file name: removes accents and
    special characters and replaces spaces with underscores.
    E.g.: "Counter-Strike: Source" -> "CounterStrike_Source".
    """
    normalized = unicodedata.normalize("NFKD", game_name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", "", ascii_name)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned or "unknown"


def get_game_name_file_path(appid: str, game_name: str) -> Path:
    filename = f"{appid}.{sanitize_game_name(game_name)}.txt"
    return get_appid_dir(appid) / filename


def write_game_name_file(appid: str, game_name: str) -> Path:
    """
    Creates <GSE Saves>/<appid>/<appid>.<game_name>.txt containing only "1".

    The file exists just to identify which game that numeric GSE Saves folder
    belongs to, so its content does not matter.
    """
    target_dir = get_appid_dir(appid)
    target_dir.mkdir(parents=True, exist_ok=True)

    target_file = get_game_name_file_path(appid, game_name)
    target_file.write_text("1", encoding="utf-8")
    return target_file
