"""
Local on-disk cache, organized as:
    cache/covers/<appid>.jpg              -> downloaded covers (shared across accounts)
    cache/info/owned_games_<steamid>.json -> account games, one file per SteamID

Storing per SteamID lets more than one account use the program on the same
machine without mixing one account's game data with another's.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

import requests

from core.constants import APP_NAME, APP_VERSION, GITHUB_URL
from core.paths import APP_DIR

logger = logging.getLogger(__name__)

CACHE_DIR = APP_DIR / "cache"
COVERS_DIR = CACHE_DIR / "covers"
INFO_DIR = CACHE_DIR / "info"
ACHIEVEMENTS_DIR = CACHE_DIR / "achievements"
NO_COVER_FILE = CACHE_DIR / "no_cover.json"
COVER_META_FILE = CACHE_DIR / "covers_meta.json"

COVER_HEADERS = {"User-Agent": f"{APP_NAME}/{APP_VERSION} (+{GITHUB_URL})"}

COVER_URL_TEMPLATES = (
    # Vertical library cover (preferred: matches the card).
    "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900.jpg",
    "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg",
    "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_hero.jpg",
    # Fallbacks used by old games / games without library art.
    "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/capsule_616x353.jpg",
    "https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
)
STORE_API_URL = "https://store.steampowered.com/api/appdetails"
COVER_TIMEOUT = 10
COVER_TTL_SECONDS = 30 * 24 * 3600  # revalidate covers every 30 days


def ensure_cache_dirs() -> None:
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    INFO_DIR.mkdir(parents=True, exist_ok=True)
    ACHIEVEMENTS_DIR.mkdir(parents=True, exist_ok=True)


# --- Per-game achievements cache (used by the individual fetch) -------------

def get_achievements_cache_path(appid: str) -> Path:
    return ACHIEVEMENTS_DIR / f"{appid}.json"


def save_playerstats_cache(appid: str, playerstats: dict) -> Path:
    """Caches the 'playerstats' dict for a game, with the current timestamp."""
    ensure_cache_dirs()
    path = get_achievements_cache_path(appid)
    payload = {"appid": str(appid), "cached_at": time.time(), "playerstats": playerstats}
    _atomic_write_json(path, payload)
    return path


def load_playerstats_cache(appid: str, ttl_seconds: int) -> dict | None:
    """
    Returns the cached 'playerstats' for a game if it is still fresh
    (within ttl_seconds since it was last updated), otherwise None.

    An expired entry is deleted, so the next fetch refreshes it.
    """
    if ttl_seconds <= 0:
        return None
    path = get_achievements_cache_path(appid)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if (time.time() - payload.get("cached_at", 0)) > ttl_seconds:
        try:
            path.unlink()
        except OSError:
            pass
        return None
    playerstats = payload.get("playerstats")
    return playerstats if isinstance(playerstats, dict) else None


def purge_expired_achievements_cache(ttl_seconds: int) -> int:
    """
    Deletes every cached achievements file older than ttl_seconds.
    Returns how many files were removed.
    """
    if ttl_seconds <= 0 or not ACHIEVEMENTS_DIR.exists():
        return 0
    now = time.time()
    removed = 0
    for file in ACHIEVEMENTS_DIR.glob("*.json"):
        try:
            with file.open("r", encoding="utf-8") as f:
                cached_at = json.load(f).get("cached_at", 0)
        except (OSError, json.JSONDecodeError):
            cached_at = 0
        if (now - cached_at) > ttl_seconds:
            try:
                file.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def clear_achievements_cache() -> int:
    """Deletes every cached game achievement file. Returns how many were removed."""
    if not ACHIEVEMENTS_DIR.exists():
        return 0
    removed = 0
    for file in ACHIEVEMENTS_DIR.glob("*.json"):
        try:
            file.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def get_cover_path(appid: str) -> Path:
    return COVERS_DIR / f"{appid}.jpg"


def get_cached_cover(appid: str) -> Path | None:
    path = get_cover_path(appid)
    return path if path.exists() else None


_IMAGE_SIGNATURES = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"GIF87a",
    b"GIF89a",
    b"BM",  # BMP
)


def _looks_like_image(content: bytes) -> bool:
    """Checks the file signature so we never save HTML/error pages."""
    if not content:
        return False
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return True
    return any(content.startswith(signature) for signature in _IMAGE_SIGNATURES)


# --- Atomic JSON helper -----------------------------------------------------

def _atomic_write_json(path: Path, data) -> None:
    """Writes JSON to a unique temp file and atomically replaces the target."""
    ensure_cache_dirs()
    tmp_file = path.with_name(f"{path.name}.{os.getpid()}_{threading.get_ident()}.tmp")
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp_file, path)


# --- Negative cover cache: AppIDs without a cover are not retried -----------

_no_cover_lock = threading.Lock()
_no_cover_cache: set[str] | None = None


def _load_no_cover_locked() -> set[str]:
    """Loads the negative cache. The caller must hold _no_cover_lock."""
    global _no_cover_cache
    if _no_cover_cache is None:
        try:
            with NO_COVER_FILE.open("r", encoding="utf-8") as f:
                _no_cover_cache = set(json.load(f))
        except (OSError, json.JSONDecodeError):
            _no_cover_cache = set()
    return _no_cover_cache


def is_no_cover(appid: str) -> bool:
    with _no_cover_lock:
        return str(appid) in _load_no_cover_locked()


def mark_no_cover(appid: str) -> None:
    try:
        with _no_cover_lock:
            _load_no_cover_locked().add(str(appid))
            _atomic_write_json(NO_COVER_FILE, sorted(_no_cover_cache))
    except OSError as exc:
        logger.warning("Could not save the no-cover cache: %s", exc)


def clear_no_cover(appid: str) -> None:
    try:
        with _no_cover_lock:
            cached = _load_no_cover_locked()
            if str(appid) not in cached:
                return
            cached.discard(str(appid))
            _atomic_write_json(NO_COVER_FILE, sorted(cached))
    except OSError as exc:
        logger.warning("Could not update the no-cover cache: %s", exc)


# --- Cover metadata (ETag / last check) ------------------------------------

_meta_lock = threading.Lock()
_meta_cache: dict | None = None


def _load_meta_locked() -> dict:
    """Loads the cover metadata. The caller must hold _meta_lock."""
    global _meta_cache
    if _meta_cache is None:
        try:
            with COVER_META_FILE.open("r", encoding="utf-8") as f:
                _meta_cache = json.load(f)
        except (OSError, json.JSONDecodeError):
            _meta_cache = {}
    return _meta_cache


def _load_meta() -> dict:
    with _meta_lock:
        return _load_meta_locked()


def _set_meta(appid: str, etag: str | None = None) -> None:
    try:
        with _meta_lock:
            meta = _load_meta_locked()
            entry = meta.setdefault(str(appid), {})
            if etag is not None:
                entry["etag"] = etag
            entry["checked"] = time.time()
            # Held under the lock so parallel downloads never write the same
            # temp file at once (which caused PermissionError on Windows).
            _atomic_write_json(COVER_META_FILE, meta)
    except OSError as exc:
        logger.warning("Could not save the cover metadata: %s", exc)


def _cover_is_fresh(appid: str) -> bool:
    entry = _load_meta().get(str(appid))
    if entry is None:
        # No metadata: assume fresh and create it (avoids re-downloading
        # every old cover at once).
        _set_meta(appid)
        return True
    return (time.time() - entry.get("checked", 0)) <= COVER_TTL_SECONDS


def _save_cover_content(appid: str, content: bytes, etag: str | None = None) -> Path:
    """Stores the image atomically (unique temp name) and updates metadata."""
    local_path = get_cover_path(appid)
    tmp_path = local_path.with_name(
        f"{local_path.name}.{os.getpid()}_{threading.get_ident()}.tmp"
    )
    tmp_path.write_bytes(content)
    os.replace(tmp_path, local_path)
    _set_meta(appid, etag)
    clear_no_cover(appid)
    return local_path


def _store_header_image(appid: str) -> str | None:
    """
    Asks the store API for the app's header/capsule image URL.

    Newer apps keep their art under a hashed path (store_item_assets) that is
    not reachable through the old CDN paths, so this is the last resort.
    """
    try:
        response = requests.get(
            STORE_API_URL,
            params={"appids": appid, "filters": "basic"},
            timeout=COVER_TIMEOUT,
            headers=COVER_HEADERS,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("Store API request failed for appid %s: %s", appid, exc)
        return None

    try:
        payload = response.json()
    except ValueError:
        return None

    data = (payload.get(str(appid)) or {}).get("data") or {}
    return data.get("header_image") or data.get("capsule_image")


def _fetch_image_content(url: str, headers: dict) -> tuple[bytes, str | None] | None:
    """Downloads and validates an image, returning (content, etag) or None."""
    try:
        response = requests.get(url, timeout=COVER_TIMEOUT, headers=headers, stream=True)
    except requests.exceptions.RequestException as exc:
        logger.warning("Image request failed (%s): %s", url, exc)
        return None

    try:
        content_type = response.headers.get("Content-Type", "")
        if response.ok and content_type.startswith("image/"):
            content = response.content
            if content and _looks_like_image(content):
                return content, response.headers.get("ETag")
    finally:
        response.close()
    return None


def download_cover(appid: str) -> Path | None:
    """
    Returns the local cover path, downloading it if needed.

    Tries the library cover first, then capsule/header, and finally the store
    API image (for newer apps whose art lives under a hashed path). Cached
    covers are reused and only revalidated (If-None-Match/HTTP 304) after the
    TTL. AppIDs known to have no cover are not retried.
    """
    ensure_cache_dirs()
    cached = get_cached_cover(appid)

    if cached is not None:
        if _cover_is_fresh(appid):
            return cached
    elif is_no_cover(appid):
        return None

    request_headers = dict(COVER_HEADERS)
    if cached is not None:
        etag = _load_meta().get(str(appid), {}).get("etag")
        if etag:
            request_headers["If-None-Match"] = etag

    network_ok = True
    for template in COVER_URL_TEMPLATES:
        url = template.format(appid=appid)
        try:
            response = requests.get(
                url, timeout=COVER_TIMEOUT, headers=request_headers, stream=True
            )
        except requests.exceptions.RequestException as exc:
            # No network: trying the other URLs (same host) is pointless.
            logger.warning("Cover request failed for appid %s: %s", appid, exc)
            network_ok = False
            break

        try:
            if cached is not None and response.status_code == 304:
                _set_meta(appid)
                return cached

            content_type = response.headers.get("Content-Type", "")
            if response.ok and content_type.startswith("image/"):
                content = response.content
                if content and _looks_like_image(content):
                    return _save_cover_content(appid, content, response.headers.get("ETag"))
        finally:
            response.close()

    # Last resort: the store API image (hashed store_item_assets path).
    if network_ok:
        store_url = _store_header_image(appid)
        if store_url:
            fetched = _fetch_image_content(store_url, dict(COVER_HEADERS))
            if fetched is not None:
                content, etag = fetched
                return _save_cover_content(appid, content, etag)

    if cached is not None:
        # Revalidation failed, but the old cover is still usable.
        _set_meta(appid)
        return cached

    logger.info("No cover found for appid %s", appid)
    mark_no_cover(appid)
    return None


def _owned_games_file(steam_id: str) -> Path:
    return INFO_DIR / f"owned_games_{steam_id}.json"


def save_owned_games_cache(steam_id: str, games: list[dict]) -> Path:
    """Saves the account game list, together with the SteamID and fetch date."""
    ensure_cache_dirs()
    payload = {
        "steamid": steam_id,
        "fetched_at": time.time(),
        "games": games,
    }
    path = _owned_games_file(steam_id)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)
    return path


def load_owned_games_cache(steam_id: str) -> list[dict] | None:
    """Returns the cached game list for that SteamID, or None if there is no cache."""
    path = _owned_games_file(steam_id)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("games")
    except (json.JSONDecodeError, OSError, AttributeError):
        return None


def list_cached_steam_ids() -> list[str]:
    """Returns every SteamID that has a cached game list."""
    ensure_cache_dirs()
    steam_ids = []
    for file in INFO_DIR.glob("owned_games_*.json"):
        steam_id = file.stem.removeprefix("owned_games_")
        steam_ids.append(steam_id)
    return steam_ids
