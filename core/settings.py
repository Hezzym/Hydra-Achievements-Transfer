"""
User settings, stored in config.json in the program folder.

When "save_data" is False, api_key and steam_id are never persisted to disk
(even if the user typed them during the current session).
"""
from __future__ import annotations

import json
import logging
import os

from core import secrets
from core.paths import APP_DIR

logger = logging.getLogger(__name__)

CONFIG_FILE = APP_DIR / "config.json"

DEFAULT_SETTINGS = {
    "api_key": "",
    "steam_id": "",
    "save_data": False,
    "create_name_file": True,
    "ignore_unplayed": True,
    "achievements_cache_ttl": 60,
    "window_size": [],
    "window_maximized": False,
}


def load_settings() -> dict:
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        try:
            merged["api_key"] = secrets.unprotect(merged.get("api_key", ""))
        except Exception:
            logger.warning("Could not read the saved API key; ignoring it.")
            merged["api_key"] = ""
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    to_save = dict(DEFAULT_SETTINGS)
    to_save.update(settings)
    if to_save.get("save_data"):
        api_key = to_save.get("api_key", "")
        if api_key:
            try:
                to_save["api_key"] = secrets.protect(api_key)
            except Exception:
                logger.warning("Could not protect the API key; storing it in plain text.")
    else:
        to_save["api_key"] = ""
        to_save["steam_id"] = ""

    # Atomic write: write to .tmp and only then replace the final file, so a
    # failure midway never corrupts config.json.
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)
    os.replace(tmp_file, CONFIG_FILE)
