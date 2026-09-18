"""
Temporary diagnostic log of AppIDs dropped or failed, grouped by reason.

Writes ``appid_failed.txt`` in the program folder (APP_DIR). Each section
shows the reason, the Steam API used (when applicable), the item/condition
that triggered it, and the affected AppIDs (comma-separated on a single line).

To disable it, set ``ENABLED = False`` below -- nothing else needs to change.
"""
from __future__ import annotations

import logging

from core.paths import APP_DIR

logger = logging.getLogger(__name__)

# Set to False to stop writing appid_failed.txt entirely.
ENABLED = True

LOG_FILE = APP_DIR / "appid_failed.txt"

API_ACHIEVEMENTS = "ISteamUserStats/GetPlayerAchievements"
API_OWNED_GAMES = "IPlayerService/GetOwnedGames"

REASON_NO_ACHIEVEMENTS = "REMOVED BY NO ACHIEVEMENTS"
REASON_NO_COMMUNITY_STATS = "REMOVED BY NO COMMUNITY-VISIBLE STATS"
REASON_UNPLAYED = "REMOVED BY NO PLAYTIME (ignore_unplayed)"
REASON_FAILED = "NOT REMOVED - FETCH FAILURE/ERROR"
REASON_PRIVATE_STATS = "NOT REMOVED - PRIVATE GAME STATS (HTTP 403)"

# (reason, api, item) -> ordered unique AppIDs
_sections: dict[tuple[str, str, str], list[str]] = {}


def log_no_achievements(appids) -> None:
    _add(REASON_NO_ACHIEVEMENTS, API_ACHIEVEMENTS, "GameHasNoStats", appids)


def log_no_community_stats(appids) -> None:
    _add(
        REASON_NO_COMMUNITY_STATS,
        API_OWNED_GAMES,
        "has_community_visible_stats = false",
        appids,
    )


def log_unplayed(appids) -> None:
    _add(REASON_UNPLAYED, API_OWNED_GAMES, "playtime_forever = 0", appids)


def log_failure(appids, item: str, api: str = API_ACHIEVEMENTS) -> None:
    _add(REASON_FAILED, api, item, appids)


def log_private_stats(appids) -> None:
    _add(REASON_PRIVATE_STATS, API_ACHIEVEMENTS, "HTTP 403", appids)


def _add(reason: str, api: str, item: str, appids) -> None:
    if not ENABLED:
        return
    bucket = _sections.setdefault((reason, api, item), [])
    for appid in appids:
        value = str(appid)
        if value and value not in bucket:
            bucket.append(value)
    _flush()


def _flush() -> None:
    blocks: list[str] = []
    for (reason, api, item), appids in _sections.items():
        if not appids:
            continue
        lines = [reason]
        if api:
            lines.append(f"API: {api}")
        if item:
            lines.append(f"ITEM: {item}")
        lines.append(", ".join(appids))
        blocks.append("\n".join(lines))
    if not blocks:
        return
    try:
        LOG_FILE.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write %s: %s", LOG_FILE.name, exc)
