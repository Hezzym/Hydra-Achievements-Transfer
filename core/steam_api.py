"""
Steam Web API client.

Covers the two endpoints used by the program:
- GetPlayerAchievements: achievements for a specific game.
- GetOwnedGames: every game on the account (installed or not).

Includes timeout and automatic retry (with backoff) for transient network
failures, and translates API errors into clear exceptions (SteamAPIError).
"""
from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

STEAM_API_TIMEOUT = 10  # seconds
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_WAIT = 5  # seconds (fallback when there is no Retry-After header)
ACHIEVEMENTS_URL = "https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/"
OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"


class SteamAPIError(Exception):
    """Error while querying the Steam Web API (network, HTTP or API error)."""


class GameHasNoStats(SteamAPIError):
    """
    The queried game has no stats/achievements.

    Not a real error: these games should simply be ignored when building the
    list of games that have achievements.
    """


class GameStatsPrivate(SteamAPIError):
    """
    The queried game's stats are private (HTTP 403).

    Not a global failure: only that specific game is inaccessible, so it can
    be counted/ignored while the other games keep being processed.
    """


def _build_session(total_retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_session = _build_session()


def _mask_key(params: dict) -> dict:
    """Returns a copy of params with the API key masked, to show errors safely."""
    masked = dict(params)
    if "key" in masked and masked["key"]:
        key = masked["key"]
        masked["key"] = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
    return masked


def _retry_after_seconds(response: requests.Response, attempt: int) -> int:
    """Figures out how long to wait after an HTTP 429 (uses Retry-After if present)."""
    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(1, int(float(header)))
        except ValueError:
            pass
    return RATE_LIMIT_WAIT * (attempt + 1)


def _get(
    url: str,
    params: dict,
    forbidden_hint: str | None = None,
    bad_request_means_no_stats: bool = False,
    forbidden_means_private: bool = False,
) -> dict:
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            response = _session.get(url, params=params, timeout=STEAM_API_TIMEOUT)
        except requests.exceptions.Timeout as exc:
            logger.warning("Steam API timeout for %s", url)
            raise SteamAPIError("The request to the Steam API timed out.") from exc
        except requests.exceptions.RequestException as exc:
            logger.warning("Steam API connection failure for %s: %s", url, exc)
            raise SteamAPIError(f"Connection to the Steam API failed: {exc}") from exc

        if response.status_code == 429:
            if attempt >= RATE_LIMIT_RETRIES:
                logger.warning("Steam API rate limit persisted for %s", url)
                raise SteamAPIError(
                    "Steam API rate limit reached (HTTP 429). Wait a moment and try again."
                )
            time.sleep(_retry_after_seconds(response, attempt))
            continue

        if response.status_code == 403:
            hint = forbidden_hint or "Invalid API key or insufficient permissions."
            logger.warning("Steam API returned 403 for %s", url)
            if forbidden_means_private:
                raise GameStatsPrivate(f"{hint} (HTTP 403)")
            raise SteamAPIError(f"{hint} (HTTP 403) Parameters sent: {_mask_key(params)}")
        if response.status_code == 400:
            # For the achievements endpoint, an HTTP 400 usually means the
            # app has no stats -- treat it as "ignore".
            if bad_request_means_no_stats:
                raise GameHasNoStats("This app has no stats/achievements (HTTP 400).")
            raise SteamAPIError(
                "Invalid request — check the filled-in fields (HTTP 400). "
                f"Parameters sent: {_mask_key(params)}"
            )
        if not response.ok:
            raise SteamAPIError(f"The Steam API returned an HTTP error {response.status_code}.")

        try:
            return response.json()
        except ValueError as exc:
            raise SteamAPIError("The API response is not valid JSON.") from exc

    raise SteamAPIError("The request to the Steam API failed after several retries.")


def get_player_achievements(appid: str, api_key: str, steam_id: str) -> dict:
    """
    Returns the API 'playerstats' dictionary, already validated.

    Raises GameHasNoStats when the game has no stats/achievements (this case
    must be ignored, not treated as an error). Raises SteamAPIError with a
    friendly message for the other errors (e.g. private profile, bad key...).
    """
    forbidden_hint = (
        "Profile or game stats are private, or the API key is invalid. "
        "If you just made the profile/stats public, Steam may take a few "
        "minutes to grant access — try again shortly."
    )
    data = _get(
        ACHIEVEMENTS_URL,
        {"appid": appid, "key": api_key, "steamid": steam_id},
        forbidden_hint=forbidden_hint,
        bad_request_means_no_stats=True,
        forbidden_means_private=True,
    )

    playerstats = data.get("playerstats", {})
    if not playerstats.get("success", False):
        error_message = playerstats.get("error", "Unknown error returned by the API.")
        lowered = error_message.lower()
        if "no stats" in lowered or "no achievements" in lowered:
            raise GameHasNoStats(error_message)
        if "not public" in lowered:
            raise GameStatsPrivate(
                error_message
                + " Make sure the profile AND the game stats are public "
                "(Profile > Edit profile > Privacy settings). If you just "
                "changed this, Steam may take a few minutes to update."
            )
        raise SteamAPIError(error_message)

    if playerstats.get("achievements") is None:
        raise GameHasNoStats("This game has no achievements or the API returned none.")

    return playerstats


def get_owned_games(api_key: str, steam_id: str) -> list[dict]:
    """
    Returns the account game list (via IPlayerService/GetOwnedGames).
    Each item usually has: appid, name, img_icon_url, playtime_forever...
    """
    data = _get(
        OWNED_GAMES_URL,
        {
            "key": api_key,
            "steamid": steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        },
    )

    games = data.get("response", {}).get("games")
    if games is None:
        raise SteamAPIError(
            "No games found. Check that your Steam profile is public and that "
            "the API key/SteamID64 are correct."
        )
    return games
