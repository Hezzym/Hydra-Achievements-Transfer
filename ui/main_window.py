"""
Main window of Hydra Achievement Transfer.

Visual layout:
- Top: 3 fields (App ID(s), API Key, SteamID) + "fetch all account games"
  button, side by side, as if they were part of the same group.
- Just below: the search field and the options.
- Middle: the game cover grid (paginated, with "load more"), with
  multi-selection (Ctrl+click).
- Footer: fetch/transfer achievement buttons (for the App ID(s) in the
  field or for all account games) + status.

User feedback happens on three layers: status text (always), sound
(success/error/info) and popup (for important events) -- so it stays clear
even when you are not looking at the footer.

The behavior is split across mixins so each concern lives in its own module:
`window_ui` (menus/layout), `library` (grid/selection), `batch`
(fetch/transfer) and `window_support` (lifecycle, settings, tray). Shared
constants and pure helpers live in `ui.helpers`.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QSystemTrayIcon

from core import settings
from ui.about_window import AboutWindow
from ui.backup_window import BackupWindow
from ui.batch import BatchMixin
from ui.batch_runner import BatchRunner
from ui.helpers import APP_TITLE, DEFAULT_WINDOW_HEIGHT, DEFAULT_WINDOW_WIDTH
from ui.library import LibraryMixin
from ui.settings_window import SettingsWindow
from ui.theme import DARK_STYLESHEET
from ui.window_support import WindowSupportMixin
from ui.window_ui import WindowUIMixin
from ui.workers import CoverDownloadWorker, OwnedGamesWorker


class MainWindow(
    WindowUIMixin,
    LibraryMixin,
    BatchMixin,
    WindowSupportMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()

        self.user_settings = settings.load_settings()

        self.all_games: list[dict] = []  # [{"appid": str, "name": str}, ...]
        self.filtered_games: list[dict] = []
        self.games_from_api = False
        self.loaded_count = 0
        self.selected_appids: list[str] = []
        self._no_achievement_appids: list[str] = []
        self._private_appids: list[str] = []
        self._no_unlocked_appids: list[str] = []
        self._pending_appids: list[str] = []
        self._syncing_selection = False

        # Active threads are kept in lists (instead of a single variable that
        # gets overwritten) so a running thread is never dropped -- this
        # avoids "QThread: Destroyed while thread is still running".
        self._cover_workers: list[CoverDownloadWorker] = []
        self._owned_games_worker: OwnedGamesWorker | None = None
        self._batch_runner = BatchRunner(self)
        self._tray: QSystemTrayIcon | None = None
        self._backup_window: BackupWindow | None = None
        self._about_window: AboutWindow | None = None
        self._settings_window: SettingsWindow | None = None

        self.setWindowTitle(APP_TITLE)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setStyleSheet(DARK_STYLESHEET)

        self._build_menu()
        self._build_ui()
        self._restore_window_size()
        self._batch_runner.no_achievements.connect(self._on_no_achievements)
        self._batch_runner.private_stats.connect(self._on_private_stats)
        self._batch_runner.no_unlocked.connect(self._on_no_unlocked)
        self._batch_runner.pending.connect(self._on_batch_pending)
        self._batch_runner.completed.connect(self._on_batch_completed)
        self._setup_tray()
        self._load_initial_state()
        self._purge_expired_achievements_cache()
