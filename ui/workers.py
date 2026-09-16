"""
QThread-based workers for network/disk work that must not block the UI:
download covers, fetch achievements (in batch) and fetch the full account
game list.
"""
from __future__ import annotations

import logging
import threading
import time
from queue import Empty, Queue

from PySide6.QtCore import QThread, Signal

from core import achievements, cache, steam_api

logger = logging.getLogger(__name__)

BATCH_BASE_DELAY = 0.15  # base interval between games
BATCH_MAX_DELAY = 3.0  # cap for the adaptive interval
COVER_MAX_WORKERS = 5  # simultaneous cover downloads


class CoverDownloadWorker(QThread):
    """
    Downloads several covers in parallel (with a limit) to speed up the list.
    Uses daemon threads, so an in-flight download never delays shutdown.
    """

    finished_one = Signal(str, object)  # appid, local_path (or None)

    def __init__(self, appids: list[str], parent=None):
        super().__init__(parent)
        self.appids = list(appids)
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        job_queue: Queue = Queue()
        for appid in self.appids:
            job_queue.put(appid)
        result_queue: Queue = Queue()

        def worker() -> None:
            while not self._stop_requested:
                try:
                    appid = job_queue.get_nowait()
                except Empty:
                    return
                try:
                    path = cache.download_cover(appid)
                except Exception:
                    logger.exception("Cover download failed for appid %s", appid)
                    path = None
                result_queue.put((appid, path))

        threads = [
            threading.Thread(target=worker, daemon=True)
            for _ in range(min(COVER_MAX_WORKERS, len(self.appids)))
        ]
        for thread in threads:
            thread.start()

        while not self._stop_requested:
            try:
                appid, path = result_queue.get(timeout=0.1)
            except Empty:
                if all(not thread.is_alive() for thread in threads):
                    break
                continue
            self.finished_one.emit(appid, str(path) if path else None)


class OwnedGamesWorker(QThread):
    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, api_key: str, steam_id: str, parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.steam_id = steam_id

    def run(self) -> None:
        try:
            games = steam_api.get_owned_games(self.api_key, self.steam_id)
            self.succeeded.emit(games)
        except steam_api.SteamAPIError as exc:
            logger.warning("Failed to fetch owned games: %s", exc)
            self.failed.emit(str(exc))
        except Exception as exc:  # extra safety against unexpected errors
            logger.exception("Unexpected error fetching owned games")
            self.failed.emit(str(exc))


class _AdaptiveRateLimiter:
    """
    Spaces out requests by keeping a minimum interval between them and
    adapts that interval: it drops on success and rises on rate limit.
    """

    def __init__(self, min_interval: float, max_interval: float):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.interval = max(0.0, min_interval)
        self._next_allowed = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        if now < self._next_allowed:
            time.sleep(self._next_allowed - now)

    def record(self) -> None:
        self._next_allowed = time.monotonic() + self.interval

    def note_success(self) -> None:
        self.interval = max(self.min_interval, self.interval * 0.85)

    def note_rate_limit(self) -> None:
        self.interval = min(self.max_interval, max(self.min_interval * 2, self.interval * 2))


class BatchFetchAndSaveAchievementsWorker(QThread):
    """
    Processes several games in two phases:

    1. Fetch: fetches each game's achievements. Games without achievements
       (GameHasNoStats) are dropped here and never reach the save phase.
    2. Save: writes files only for the games that passed the fetch.

    Errors on one game do not stop the others (except rate limit, which
    aborts the rest to avoid making things worse). The process can be
    canceled through cancel().
    """

    progress = Signal(int, int, str, str)  # current (1-based), total, label, phase
    no_achievements = Signal(str)  # appid of a game with no achievements
    preview_ready = Signal(list)  # [(label, gained, lost, is_new), ...] before saving
    pending = Signal(list)  # appids that did not succeed (for a resume)
    completed = Signal(int, int, list, bool)  # saved, failed, [(name, msg)], canceled

    FETCH_PHASE = "fetch"
    SAVE_PHASE = "save"

    def __init__(
        self,
        items: list[tuple[str, str]],
        api_key: str,
        steam_id: str,
        create_name_file: bool = True,
        request_delay: float = BATCH_BASE_DELAY,
        cache_ttl_seconds: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.items = items
        self.api_key = api_key
        self.steam_id = steam_id
        self.create_name_file = create_name_file
        self.request_delay = request_delay
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cancel_requested = False
        self._preview_event = threading.Event()
        self._preview_proceed = True

    def cancel(self) -> None:
        self._cancel_requested = True

    def resolve_preview(self, proceed: bool) -> None:
        """Called by the UI to answer the preview confirmation."""
        self._preview_proceed = proceed
        self._preview_event.set()

    def run(self) -> None:
        limiter = _AdaptiveRateLimiter(self.request_delay, BATCH_MAX_DELAY)
        failures: list[tuple[str, str]] = []
        fetched: list[tuple[str, str, dict]] = []
        canceled = False
        no_achievement_set: set[str] = set()
        saved_set: set[str] = set()

        # --- Phase 1: fetch (with handling of games without achievements) ------
        total = len(self.items)
        for index, (appid, name) in enumerate(self.items, start=1):
            if self._cancel_requested:
                canceled = True
                break

            label = name or appid
            self.progress.emit(index, total, label, self.FETCH_PHASE)

            # Reuse the cached achievements while they are still fresh.
            cached_stats = cache.load_playerstats_cache(appid, self.cache_ttl_seconds)
            if cached_stats is not None:
                fetched.append((appid, label, cached_stats))
                continue

            limiter.wait()
            try:
                playerstats = steam_api.get_player_achievements(appid, self.api_key, self.steam_id)
                if self.cache_ttl_seconds > 0:
                    cache.save_playerstats_cache(appid, playerstats)
                limiter.note_success()
            except steam_api.GameHasNoStats:
                # No achievements: drop the game (it does not enter the list).
                limiter.note_success()
                no_achievement_set.add(appid)
                self.no_achievements.emit(appid)
                continue
            except steam_api.SteamAPIError as exc:
                message = str(exc)
                rate_limited = "rate limit" in message.lower()
                if rate_limited:
                    limiter.note_rate_limit()
                else:
                    limiter.note_success()
                failures.append((label, message))
                if rate_limited:
                    for skipped_appid, skipped_name in self.items[index:]:
                        failures.append(
                            (skipped_name or skipped_appid, "Skipped: Steam API rate limit reached.")
                        )
                    break
                continue
            except Exception as exc:  # extra safety against unexpected errors
                logger.exception("Unexpected error fetching achievements for appid %s", appid)
                limiter.note_success()
                failures.append((label, str(exc)))
                continue
            finally:
                limiter.record()

            fetched.append((appid, label, playerstats))

        # --- Preview: compare with the current files before writing -----------
        if fetched and not canceled:
            diffs = []
            for appid, label, playerstats in fetched:
                converted = achievements.convert_to_gse_format(playerstats)
                old = achievements.read_achievements_file(appid)
                gained, lost = achievements.diff_achievements(old, converted)
                diffs.append((label, len(gained), len(lost), old is None))

            self._preview_event.clear()
            self._preview_proceed = True
            self.preview_ready.emit(diffs)
            # Wait for the UI answer (also wakes up to honor cancel()).
            while not self._preview_event.wait(0.1):
                if self._cancel_requested:
                    break
            if not self._preview_proceed or self._cancel_requested:
                canceled = True

        # --- Phase 2: save (only the games that passed the fetch) --------------
        saved = 0
        if not canceled:
            save_total = len(fetched)
            for position, (appid, label, playerstats) in enumerate(fetched, start=1):
                if self._cancel_requested:
                    canceled = True
                    break

                self.progress.emit(position, save_total, label, self.SAVE_PHASE)
                try:
                    converted = achievements.convert_to_gse_format(playerstats)
                    achievements.write_achievements_file(appid, converted)

                    if self.create_name_file:
                        game_name = playerstats.get("gameName") or appid
                        achievements.write_game_name_file(appid, game_name)

                    saved += 1
                    saved_set.add(appid)
                except Exception as exc:
                    logger.exception("Failed to save achievements for appid %s", appid)
                    failures.append((label, str(exc)))

        pending = [
            appid
            for appid, _name in self.items
            if appid not in saved_set and appid not in no_achievement_set
        ]

        logger.info(
            "Batch finished: %d saved, %d failed, canceled=%s", saved, len(failures), canceled
        )
        self.pending.emit(pending)
        self.completed.emit(saved, len(failures), failures, canceled)
