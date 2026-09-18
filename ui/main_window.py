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
"""
from __future__ import annotations

import re

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import appid_log, cache, settings, steam_paths
from core.constants import (
    APIKEY_URL,
    APP_NAME,
    READ_BEFORE_USE_URL,
    STEAM_ACHIEVEMENTS_URL,
    STEAMDB_URL,
    STEAMID_URL,
)
from ui import labels, sounds
from ui.about_window import AboutWindow
from ui.backup_window import BackupWindow
from ui.batch_runner import BatchRunner
from ui.settings_window import SettingsWindow
from ui.theme import COLOR_ERROR, COLOR_SUCCESS, DARK_STYLESHEET
from ui.widgets.field_with_link import ComboFieldWithLink, FieldWithLink
from ui.widgets.game_grid import APPID_ROLE, GameGrid
from ui.widgets.help_hint import HelpHint
from ui.widgets.selected_panel import SelectedPanel
from ui.workers import CoverDownloadWorker, OwnedGamesWorker

APP_TITLE = APP_NAME
PAGE_SIZE = 50
SEARCH_DEBOUNCE_MS = 200
DEFAULT_WINDOW_WIDTH = 1150
DEFAULT_WINDOW_HEIGHT = 760


def parse_appids(text: str) -> list[str]:
    """Splits an AppID list typed as '111, 222 333' into unique items."""
    items = re.split(r"[,\s;]+", text.strip())
    appids: list[str] = []
    for item in items:
        item = item.strip()
        if item and item not in appids:
            appids.append(item)
    return appids


def _make_clear_icon(color: str = "#9a9a9a", size: int = 16) -> QIcon:
    """Draws a small themed 'x' icon for the search clear action."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(QColor(color), 2))
    margin = size // 4
    painter.drawLine(margin, margin, size - margin, size - margin)
    painter.drawLine(size - margin, margin, margin, size - margin)
    painter.end()
    return QIcon(pixmap)


def _separator() -> QLabel:
    """A subtle vertical bar used to visually separate groups of options."""
    label = QLabel("|")
    label.setProperty("role", "separator")
    return label


class MainWindow(QMainWindow):
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
        self._load_initial_state()
        self._purge_expired_achievements_cache()

    # ------------------------------------------------------------------ UI

    def _build_menu(self) -> None:
        menubar: QMenuBar = self.menuBar()
        backup_action = menubar.addAction("Backup")
        backup_action.triggered.connect(self._open_backup_window)

        read_action = menubar.addAction(labels.MENU_READ_BEFORE_USE)
        read_action.triggered.connect(self._open_read_before_use)

        settings_action = menubar.addAction(labels.MENU_SETTINGS)
        settings_action.triggered.connect(self._open_settings_window)

        about_action = menubar.addAction("About")
        about_action.triggered.connect(self._open_about_window)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # --- Top group: 3 fields + "fetch all account games" button -------------
        # They are grouped visually because the "fetch all account games"
        # action depends directly on the API Key and SteamID filled in above,
        # so it makes sense for it to look like part of the same block.
        fields_layout = QHBoxLayout()
        fields_layout.setSpacing(16)

        self.field_appid = FieldWithLink(labels.FIELD_APPID, labels.FIELD_APPID_LINK, STEAMDB_URL)
        self.field_appid.input.setPlaceholderText(labels.FIELD_APPID_PLACEHOLDER)
        self.field_apikey = FieldWithLink(labels.FIELD_APIKEY, labels.FIELD_APIKEY_LINK, APIKEY_URL)
        self.field_apikey.input.setEchoMode(QLineEdit.Password)

        self.field_userid = ComboFieldWithLink(
            labels.FIELD_USERID, labels.FIELD_USERID_LINK, STEAMID_URL
        )

        self.field_appid.input.textChanged.connect(self._on_appid_manual_change)

        fields_layout.addWidget(self.field_appid, stretch=2)
        fields_layout.addWidget(self.field_apikey, stretch=2)
        fields_layout.addWidget(self.field_userid, stretch=2)

        # The button is aligned with the text fields (not with the label above
        # them), so it goes inside a QVBoxLayout with a spacer the same size
        # as the label.
        fetch_owned_games_column = QVBoxLayout()
        fetch_owned_games_column.setSpacing(4)
        spacer_label = QLabel(" ")
        self.button_fetch_owned_games = QPushButton("Fetch all games from account")
        self.button_fetch_owned_games.setProperty("role", "secondary")
        self.button_fetch_owned_games.clicked.connect(self._on_fetch_owned_games_clicked)
        fetch_owned_games_column.addWidget(spacer_label)
        fetch_owned_games_column.addWidget(self.button_fetch_owned_games)
        fetch_owned_games_column.addStretch(1)
        fields_layout.addLayout(fetch_owned_games_column, stretch=1)

        root_layout.addLayout(fields_layout)

        # --- Options (single row, separated by '|') -----------------------------
        options_layout = QHBoxLayout()
        options_layout.setSpacing(10)

        self.checkbox_save_data = QCheckBox(labels.SAVE_API_CHECKBOX)
        self.checkbox_save_data.setChecked(self.user_settings.get("save_data", False))
        options_layout.addWidget(self.checkbox_save_data)
        options_layout.addWidget(_separator())

        self.checkbox_create_name_file = QCheckBox(labels.CREATE_NAME_CHECKBOX)
        self.checkbox_create_name_file.setChecked(self.user_settings.get("create_name_file", True))
        options_layout.addWidget(self.checkbox_create_name_file)
        self.help_create_name_file = HelpHint(
            labels.CREATE_NAME_HELP_TITLE,
            labels.CREATE_NAME_HELP,
        )
        options_layout.addWidget(self.help_create_name_file)
        options_layout.addWidget(_separator())

        self.checkbox_ignore_unplayed = QCheckBox(labels.IGNORE_UNPLAYED_CHECKBOX)
        self.checkbox_ignore_unplayed.setChecked(self.user_settings.get("ignore_unplayed", True))
        options_layout.addWidget(self.checkbox_ignore_unplayed)
        self.help_ignore_unplayed = HelpHint(
            labels.IGNORE_UNPLAYED_HELP_TITLE,
            labels.IGNORE_UNPLAYED_HELP,
        )
        options_layout.addWidget(self.help_ignore_unplayed)
        options_layout.addStretch(1)
        root_layout.addLayout(options_layout)

        # --- Search -------------------------------------------------------------
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(labels.SEARCH_PLACEHOLDER)
        self.search_clear_action = self.search_input.addAction(
            _make_clear_icon(), QLineEdit.TrailingPosition
        )
        self.search_clear_action.setToolTip("Clear search")
        self.search_clear_action.setVisible(False)
        self.search_clear_action.triggered.connect(self.search_input.clear)
        root_layout.addWidget(self.search_input)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._apply_filter_and_reload)
        self.search_input.textChanged.connect(lambda _text: self._search_timer.start())
        self.search_input.textChanged.connect(
            lambda text: self.search_clear_action.setVisible(bool(text))
        )

        # --- Selected games section ---------------------------------------------
        self.selected_panel = SelectedPanel()
        self.selected_panel.remove_requested.connect(self._on_remove_selected)
        self.selected_panel.clear_requested.connect(self._on_clear_selection)
        root_layout.addWidget(self.selected_panel)

        # --- Games toolbar: sort + installed filter -----------------------------
        games_toolbar = QHBoxLayout()
        games_toolbar.setSpacing(10)

        games_toolbar.addWidget(QLabel(labels.SORT_BY))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem(labels.SORT_PLAYTIME, "playtime")
        self.sort_combo.addItem(labels.SORT_NAME, "name")
        self.sort_combo.currentIndexChanged.connect(lambda *_: self._apply_filter_and_reload())
        games_toolbar.addWidget(self.sort_combo)

        self.installed_only = QCheckBox(labels.FILTER_INSTALLED_ONLY)
        self.installed_only.toggled.connect(lambda *_: self._apply_filter_and_reload())
        games_toolbar.addWidget(self.installed_only)

        games_toolbar.addStretch(1)
        root_layout.addLayout(games_toolbar)

        # --- Virtualized cover grid ---------------------------------------------
        self.grid = GameGrid()
        self.grid.selectionModel().selectionChanged.connect(self._on_grid_selection_changed)
        self.grid.link_activated.connect(self._on_open_steam_link)
        self.grid.load_more_requested.connect(self._load_more_cards)
        root_layout.addWidget(self.grid, stretch=1)

        # --- Footer: fetch/transfer + status ------------------------------------
        footer_buttons = QHBoxLayout()
        footer_buttons.setSpacing(12)

        self.button_fetch_save = QPushButton(f"{labels.FETCH_TRANSFER} (0)")
        self.button_fetch_save.clicked.connect(self._on_fetch_save_clicked)
        footer_buttons.addWidget(self.button_fetch_save, stretch=2)

        self.button_save_all = QPushButton(labels.TRANSFER_ALL)
        self.button_save_all.setProperty("role", "secondary")
        self.button_save_all.clicked.connect(self._on_save_all_clicked)
        footer_buttons.addWidget(self.button_save_all, stretch=1)

        self.button_resume = QPushButton(f"{labels.RESUME_BATCH} (0)")
        self.button_resume.setProperty("role", "secondary")
        self.button_resume.clicked.connect(self._on_resume_clicked)
        self.button_resume.setVisible(False)
        footer_buttons.addWidget(self.button_resume, stretch=1)

        self.status_label = QLabel("Ready.")
        root_layout.addWidget(self.status_label)

        root_layout.addLayout(footer_buttons)

    # ------------------------------------------------------------- estado inicial

    def _load_initial_state(self) -> None:
        steam_path = steam_paths.find_steam_path()
        installed_appids: list[str] = []
        installed_games: list[dict] = []
        local_users: list[tuple[str, str]] = []
        user_infos: list[dict] = []

        if steam_path is not None:
            installed_appids = steam_paths.get_installed_appids(steam_path)
            for appid in installed_appids:
                installed_games.append(
                    {"appid": appid, "name": appid, "playtime_forever": 0, "installed": True}
                )
            user_infos = steam_paths.get_local_users(steam_path)
            for user in user_infos:
                label = user["persona_name"] or user["account_name"] or user["steamid"]
                local_users.append((user["steamid"], f"{label} ({user['steamid']})"))

        self._installed_ids = set(installed_appids)

        # Fill the combo options BEFORE restoring saved values, so the saved
        # value can be correctly matched to a list item
        # (see ComboFieldWithLink.set_options).
        self.field_userid.set_options(local_users)

        if self.user_settings.get("save_data"):
            self.field_apikey.set_text(self.user_settings.get("api_key", ""))
            self.field_userid.set_text(self.user_settings.get("steam_id", ""))

        # Figure out which SteamID to use for restoring the game cache.
        active_steam_id = self.field_userid.text()
        if not active_steam_id:
            active_steam_id = self._resolve_active_steam_id(user_infos)

        # If there is already an "all account games" cache for that SteamID,
        # it becomes the displayed list (including games not installed).
        # Without a cache, fall back to the installed games found on the machine.
        owned_cache = cache.load_owned_games_cache(active_steam_id) if active_steam_id else None
        self.games_from_api = bool(owned_cache)
        if owned_cache:
            self.all_games = [self._game_entry(g) for g in owned_cache]
        else:
            self.all_games = installed_games

        self._set_status("Ready.")
        self._apply_filter_and_reload()

    @staticmethod
    def _resolve_active_steam_id(users: list[dict]) -> str:
        """
        Picks which local SteamID to use for loading the cached game list.

        Prefers the most recently used account that already has a cache, then
        a single local user / single cache, then the most recent account.
        """
        cached_ids = set(cache.list_cached_steam_ids())
        ordered = sorted(
            users,
            key=lambda u: (u.get("most_recent", False), u.get("timestamp", 0)),
            reverse=True,
        )
        for user in ordered:
            if user["steamid"] in cached_ids:
                return user["steamid"]
        if len(users) == 1:
            return users[0]["steamid"]
        if len(cached_ids) == 1:
            return next(iter(cached_ids))
        if ordered:
            return ordered[0]["steamid"]
        return ""

    def _game_entry(self, game: dict) -> dict:
        """Normalizes a game dict, keeping playtime and the installed flag."""
        appid = str(game.get("appid"))
        try:
            playtime = int(game.get("playtime_forever", 0) or 0)
        except (TypeError, ValueError):
            playtime = 0
        return {
            "appid": appid,
            "name": game.get("name", appid),
            "playtime_forever": playtime,
            "installed": appid in getattr(self, "_installed_ids", set()),
            "has_community_visible_stats": bool(game.get("has_community_visible_stats", False)),
        }

    # --------------------------------------------------------------- grid/cards

    def _clear_grid(self) -> None:
        self._syncing_selection = True
        self.grid.set_games([])
        self._syncing_selection = False
        self.loaded_count = 0

    def _load_more_cards(self) -> None:
        next_batch = self.filtered_games[self.loaded_count : self.loaded_count + PAGE_SIZE]
        self.grid.append_games(next_batch)

        appids_to_download = []
        for game in next_batch:
            appid = game["appid"]
            # Covers already in cache are loaded right away (no thread, no
            # "..." flicker); only the missing ones go to the download worker.
            cached_cover = cache.get_cached_cover(appid)
            if cached_cover is not None:
                pixmap = QPixmap(str(cached_cover))
                if not pixmap.isNull():
                    self.grid.set_cover(appid, pixmap)
                    continue
                # Corrupted cache cover: remove it so it is downloaded again.
                try:
                    cached_cover.unlink()
                except OSError:
                    pass
            appids_to_download.append(appid)

        self.loaded_count += len(next_batch)
        self.grid.set_load_more(self.loaded_count < len(self.filtered_games))

        # Re-apply the selection (newly inserted items may be selected).
        self._syncing_selection = True
        self._select_appids_in_view(self.selected_appids)
        self._syncing_selection = False
        self._update_transfer_button()

        if appids_to_download:
            worker = CoverDownloadWorker(appids_to_download, parent=self)
            worker.finished_one.connect(self._on_cover_downloaded)
            worker.finished.connect(lambda w=worker: self._on_cover_worker_finished(w))
            self._cover_workers.append(worker)
            worker.start()

    def _on_cover_worker_finished(self, worker: CoverDownloadWorker) -> None:
        # Remove the thread from the active list as soon as it finishes, and
        # schedule safe cleanup of the Qt object.
        if worker in self._cover_workers:
            self._cover_workers.remove(worker)
        worker.deleteLater()

    def _on_cover_downloaded(self, appid: str, path: str | None) -> None:
        if not path:
            return
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.grid.set_cover(appid, pixmap)

    def _on_grid_selection_changed(self, *_args) -> None:
        if self._syncing_selection:
            return

        model = self.grid.model()
        model_appids = model.appids()
        visible = set(model_appids)
        view_selected = {
            model.data(index, APPID_ROLE)
            for index in self.grid.selectionModel().selectedIndexes()
        }

        # Selections for games currently hidden (e.g. filtered out by a search)
        # are kept; the view's state only applies to the visible items. This
        # way selecting after a search does not drop earlier selections.
        kept = [appid for appid in self.selected_appids if appid not in visible]
        ordered = [appid for appid in model_appids if appid in view_selected]
        self.selected_appids = kept + ordered

        self._update_transfer_button()
        self._syncing_selection = True
        self.field_appid.set_text(", ".join(self.selected_appids))
        self._syncing_selection = False

    def _select_appids_in_view(self, appids: list[str]) -> None:
        selection = QItemSelection()
        for appid in appids:
            row = self.grid.model().row_for_appid(appid)
            if row >= 0:
                index = self.grid.model().index(row, 0)
                selection.select(index, index)
        self.grid.selectionModel().select(
            selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows
        )

    def _update_transfer_button(self) -> None:
        count = len(self.selected_appids)
        if hasattr(self, "button_fetch_save"):
            self.button_fetch_save.setText(f"{labels.FETCH_TRANSFER} ({count})")
        if hasattr(self, "selected_panel"):
            self.selected_panel.set_selected(self._selected_games())

    def _selected_games(self) -> list[dict]:
        name_by_appid = {g["appid"]: g.get("name", g["appid"]) for g in self.all_games}
        return [
            {"appid": appid, "name": name_by_appid.get(appid, appid)}
            for appid in self.selected_appids
        ]

    def _on_remove_selected(self, appid: str) -> None:
        if appid in self.selected_appids:
            self.selected_appids.remove(appid)
        self._syncing_selection = True
        self._select_appids_in_view(self.selected_appids)
        self._syncing_selection = False
        self._update_transfer_button()

    def _on_clear_selection(self) -> None:
        self.selected_appids = []
        self._syncing_selection = True
        self._select_appids_in_view([])
        self._syncing_selection = False
        self._update_transfer_button()

    def _on_appid_manual_change(self, text: str) -> None:
        # Keeps the grid selection in sync with what is typed in the field
        # (AppIDs separated by comma/space).
        if self._syncing_selection:
            return
        self.selected_appids = parse_appids(text)
        self._syncing_selection = True
        self._select_appids_in_view(self.selected_appids)
        self._syncing_selection = False
        self._update_transfer_button()

    def _apply_filter_and_reload(self) -> None:
        text = self.search_input.text().strip().lower()
        installed_only = (
            self.installed_only.isChecked() if hasattr(self, "installed_only") else False
        )
        sort_mode = self.sort_combo.currentData() if hasattr(self, "sort_combo") else "playtime"

        games = list(self.all_games)
        if text:
            games = [
                g
                for g in games
                if text in g["appid"].lower() or text in g.get("name", "").lower()
            ]
        if installed_only:
            games = [g for g in games if g.get("installed")]

        self.filtered_games = self._sort_games(games, sort_mode)
        self._clear_grid()
        self._load_more_cards()

    @staticmethod
    def _sort_games(games: list[dict], mode: str) -> list[dict]:
        """Reorders the list: by playtime (most first) or by name (A-Z)."""
        if mode == "name":
            return sorted(games, key=lambda g: g.get("name", "").lower())
        return sorted(games, key=lambda g: g.get("playtime_forever", 0), reverse=True)

    # ------------------------------------------------------------------ backup

    def _open_backup_window(self) -> None:
        if self._backup_window is None:
            self._backup_window = BackupWindow(parent=self)
        self._backup_window.show()
        self._backup_window.raise_()
        self._backup_window.activateWindow()

    # ------------------------------------------------------------------- about

    def _open_about_window(self) -> None:
        if self._about_window is None:
            self._about_window = AboutWindow(parent=self)
        self._about_window.show()
        self._about_window.raise_()
        self._about_window.activateWindow()

    # ---------------------------------------------------------- read before use

    def _open_read_before_use(self) -> None:
        QDesktopServices.openUrl(QUrl(READ_BEFORE_USE_URL))

    # ----------------------------------------------------------------- settings

    def _open_settings_window(self) -> None:
        if self._settings_window is None:
            self._settings_window = SettingsWindow(
                self.user_settings.get("achievements_cache_ttl", 60), parent=self
            )
            self._settings_window.ttl_changed.connect(self._on_achievements_ttl_changed)
            self._settings_window.reset_requested.connect(self._on_reset_achievements_cache)
        self._settings_window.spin.blockSignals(True)
        self._settings_window.spin.setValue(
            int(self.user_settings.get("achievements_cache_ttl", 60))
        )
        self._settings_window.spin.blockSignals(False)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

        removed = self._purge_expired_achievements_cache()
        if removed:
            self._settings_window.set_status(
                labels.SETTINGS_EXPIRED_REMOVED.format(count=removed)
            )

    def _achievements_ttl_seconds(self) -> int:
        return max(0, int(self.user_settings.get("achievements_cache_ttl", 60))) * 60

    def _purge_expired_achievements_cache(self) -> int:
        return cache.purge_expired_achievements_cache(self._achievements_ttl_seconds())

    def _on_achievements_ttl_changed(self, minutes: int) -> None:
        self.user_settings["achievements_cache_ttl"] = int(minutes)
        settings.save_settings(self._collect_settings())

        removed = self._purge_expired_achievements_cache()
        message = labels.SETTINGS_TTL_UPDATED.format(minutes=int(minutes))
        if removed:
            message += " " + labels.SETTINGS_EXPIRED_REMOVED.format(count=removed)
        if self._settings_window is not None:
            self._settings_window.set_status(message)

    def _on_reset_achievements_cache(self) -> None:
        removed = cache.clear_achievements_cache()
        if self._settings_window is not None:
            self._settings_window.set_status(
                labels.SETTINGS_CACHE_CLEARED.format(count=removed)
            )

    # ----------------------------------------------------------------- actions

    def _on_open_steam_link(self, appid: str) -> None:
        steam_id = self.field_userid.text()
        if not steam_id:
            self._notify_error("Fill in the SteamID to open the Steam page.")
            return
        url = STEAM_ACHIEVEMENTS_URL.format(steam_id=steam_id, appid=appid)
        QDesktopServices.openUrl(QUrl(url))

    def _on_fetch_owned_games_clicked(self) -> None:
        api_key = self.field_apikey.text()
        steam_id = self.field_userid.text()
        if not api_key or not steam_id:
            self._notify_error("Please fill in App ID, API Key and SteamID.")
            return

        cache.clear_achievements_cache()

        self._set_status("Fetching all games from your account...")
        self._set_fetch_in_progress(True)

        self._owned_games_worker = OwnedGamesWorker(api_key, steam_id, parent=self)
        self._owned_games_worker.succeeded.connect(self._on_owned_games_fetched)
        self._owned_games_worker.failed.connect(self._on_owned_games_failed)
        self._owned_games_worker.finished.connect(self._on_owned_games_worker_finished)
        self._owned_games_worker.start()

    def _set_fetch_in_progress(self, in_progress: bool) -> None:
        """Blocks the transfer actions while the account games are being fetched."""
        self.button_fetch_owned_games.setEnabled(not in_progress)
        self.button_fetch_save.setEnabled(not in_progress)
        self.button_save_all.setEnabled(not in_progress)

    def _on_owned_games_worker_finished(self) -> None:
        # Drop the reference first (the C++ object is about to be deleted),
        # so closeEvent never calls isRunning() on a deleted object.
        worker = self._owned_games_worker
        self._owned_games_worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_fetch_in_progress(False)

    def _on_owned_games_fetched(self, games: list[dict]) -> None:
        entries = [self._game_entry(g) for g in games]

        # Only games with visible community stats are kept.
        without_stats = [g for g in entries if not g.get("has_community_visible_stats", False)]
        ignored_no_stats = len(without_stats)
        appid_log.log_no_community_stats([g["appid"] for g in without_stats])
        entries = [g for g in entries if g.get("has_community_visible_stats", False)]

        ignored = 0
        if self.checkbox_ignore_unplayed.isChecked():
            unplayed = [g for g in entries if g.get("playtime_forever", 0) <= 0]
            ignored = len(unplayed)
            appid_log.log_unplayed([g["appid"] for g in unplayed])
            entries = [g for g in entries if g.get("playtime_forever", 0) > 0]

        self.all_games = entries
        self.selected_appids = []
        self.field_appid.set_text("")

        # Persist the (possibly filtered) list so the cache only keeps the
        # relevant games.
        steam_id = self.field_userid.text()
        if steam_id:
            try:
                cache.save_owned_games_cache(steam_id, self.all_games)
            except OSError:
                pass

        self._apply_filter_and_reload()

        removed_lines: list[str] = []
        if ignored:
            removed_lines.append(f"{ignored} unplayed game(s) were ignored.")
        if ignored_no_stats:
            removed_lines.append(
                f"{ignored_no_stats} game(s) without Steam achievements were ignored."
            )
        saved_line = f"Account games fetched and cached ({len(self.all_games)} game(s))."

        status_html = "<br>".join(
            f'<span style="color:{COLOR_ERROR}">{line}</span>' for line in removed_lines
        )
        if status_html:
            status_html += "<br><br>"
        status_html += f'<span style="color:{COLOR_SUCCESS}">{saved_line}</span>'
        self._set_status(status_html, html=True)

        message = "\n".join(removed_lines)
        if message:
            message += "\n\n"
        message += saved_line
        sounds.play_success()
        QMessageBox.information(self, APP_TITLE, message)

    def _on_owned_games_failed(self, error: str) -> None:
        self._notify_error(f"Error: {error}")

    def _on_fetch_save_clicked(self) -> None:
        appids = parse_appids(self.field_appid.text())
        if not appids:
            self._notify_error("Please select at least one game or fill in an App ID.")
            return

        confirm = QMessageBox.question(
            self,
            APP_TITLE,
            f"You selected {len(appids)} game(s).\n\nDo you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self._start_batch(appids)

    def _on_save_all_clicked(self) -> None:
        if not self.all_games:
            self._notify_error("No games loaded. Use 'Fetch all games from account' first.")
            return

        count = len(self.all_games)
        confirm = QMessageBox.question(
            self,
            APP_TITLE,
            "Don't forget to run 'Fetch all games from account' before using this "
            f"option.\n\nThis will transfer achievements for {count} game(s).\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self._start_batch([g["appid"] for g in self.all_games])

    def _start_batch(self, appids: list[str]) -> None:
        api_key = self.field_apikey.text()
        steam_id = self.field_userid.text()

        if not api_key or not steam_id:
            self._notify_error("Please fill in API Key and SteamID.")
            return

        if not steam_id.isdigit():
            self._notify_error(f"Invalid SteamID: '{steam_id}' (must contain only numbers).")
            return

        invalid = [appid for appid in appids if not appid.isdigit()]
        if invalid:
            self._notify_error("Invalid App ID(s): " + ", ".join(invalid))
            return

        settings.save_settings(self._collect_settings())

        name_by_appid = {g["appid"]: g.get("name", g["appid"]) for g in self.all_games}
        items = [(appid, name_by_appid.get(appid, appid)) for appid in appids]

        self._no_achievement_appids = []
        self._private_appids = []
        self._no_unlocked_appids = []
        self._pending_appids = []
        self._update_resume_button()
        self._batch_runner.start(
            items,
            api_key,
            steam_id,
            self.checkbox_create_name_file.isChecked(),
            self,
            cache_ttl_seconds=self._achievements_ttl_seconds(),
        )

    def _on_no_achievements(self, appid: str) -> None:
        self._no_achievement_appids.append(appid)

    def _on_private_stats(self, appids: list) -> None:
        self._private_appids = [str(appid) for appid in appids]

    def _on_no_unlocked(self, appids: list) -> None:
        self._no_unlocked_appids = [str(appid) for appid in appids]

    def _on_batch_pending(self, appids: list) -> None:
        self._pending_appids = [str(appid) for appid in appids]
        self._update_resume_button()

    def _update_resume_button(self) -> None:
        if not hasattr(self, "button_resume"):
            return
        count = len(self._pending_appids)
        self.button_resume.setText(f"{labels.RESUME_BATCH} ({count})")
        self.button_resume.setVisible(count > 0)

    def _on_resume_clicked(self) -> None:
        if self._pending_appids:
            self._start_batch(list(self._pending_appids))

    def _prune_games_from_list(self, appids: list[str]) -> None:
        """
        Removes the given AppIDs from the loaded list, without rebuilding the
        rest. Persists the cache when the list came from the API.
        """
        if not appids:
            return
        removed_set = set(appids)
        new_all_games = [g for g in self.all_games if g["appid"] not in removed_set]
        if len(new_all_games) != len(self.all_games):
            self.all_games = new_all_games
            self.selected_appids = [a for a in self.selected_appids if a not in removed_set]
            self.field_appid.set_text(", ".join(self.selected_appids))
            self._apply_filter_and_reload()

        steam_id = self.field_userid.text()
        if steam_id and self.games_from_api:
            try:
                cache.save_owned_games_cache(steam_id, self.all_games)
            except OSError:
                pass

    def _prune_removed_games(self) -> tuple[list[str], list[str], list[str]]:
        """
        Removes from the list the games dropped in the last batch: those with
        no achievements, those with private stats and those with no unlocked
        achievements.

        Returns (no_achievements, private, no_unlocked).
        """
        no_achievements = list(self._no_achievement_appids)
        private = list(self._private_appids)
        no_unlocked = list(self._no_unlocked_appids)
        self._no_achievement_appids = []
        self._private_appids = []
        self._no_unlocked_appids = []
        if no_achievements:
            appid_log.log_no_achievements(no_achievements)
        self._prune_games_from_list(no_achievements + private + no_unlocked)
        return no_achievements, private, no_unlocked

    def _on_batch_completed(self, saved: int, failed: int, failures: list, canceled: bool) -> None:
        no_achievement_removed, private_removed, no_unlocked_removed = (
            self._prune_removed_games()
        )
        self._update_resume_button()

        # Everything that was not saved is listed first (in red); the "Saved"
        # line is always last (in green), separated by a blank line.
        details: list[str] = []
        if canceled:
            details.append("Canceled.")
        if failed:
            details.append(f"{failed} game(s) failed.")
        if no_achievement_removed:
            details.append(f"{len(no_achievement_removed)} game(s) have no achievements were removed.")
        if private_removed:
            details.append(f"{len(private_removed)} game(s) have private game stats were removed.")
        if no_unlocked_removed:
            details.append(
                f"{len(no_unlocked_removed)} game(s) have no unlocked achievements were removed."
            )
        if self._pending_appids:
            details.append(
                f"{len(self._pending_appids)} game(s) pending — use "
                "'Resume interrupted' to retry."
            )

        saved_line = f"Saved achievements for {saved} game(s)."

        # Severity rules: error when nothing was saved, warning when some games
        # saved and some failed, success when nothing failed and at least one
        # game was saved.
        if failed and saved == 0:
            severity = "error"
        elif failed:
            severity = "warning"
        elif saved:
            severity = "success"
        else:
            severity = "warning"

        # Status label: everything in red except the "Saved" line, in green.
        detail_spans = [
            f'<span style="color:{COLOR_ERROR}">{text}</span>' for text in details
        ]
        saved_span = f'<span style="color:{COLOR_SUCCESS}">{saved_line}</span>'
        status_html = "<br>".join(detail_spans)
        if status_html:
            status_html += "<br><br>"
        status_html += saved_span
        self._set_status(status_html, error=(severity == "error"), html=True)

        # Popup: same order as the label, with the per-game failure details
        # inserted before the "Saved" line.
        popup_lines = list(details)
        if failures:
            visible = failures[:10]
            popup_lines.extend(f"- {name}: {reason}" for name, reason in visible)
            hidden = len(failures) - len(visible)
            if hidden > 0:
                popup_lines.append(f"... and {hidden} more.")
        popup_text = "\n".join(popup_lines)
        if popup_text:
            popup_text += "\n\n"
        popup_text += saved_line

        if severity == "error":
            sounds.play_error()
            QMessageBox.critical(self, APP_TITLE, popup_text)
        elif severity == "warning":
            sounds.play_info()
            QMessageBox.warning(self, APP_TITLE, popup_text)
        else:
            sounds.play_success()
            QMessageBox.information(self, APP_TITLE, popup_text)

    # ------------------------------------------------------------------ helpers

    def _restore_window_size(self) -> None:
        size = self.user_settings.get("window_size") or []
        try:
            width, height = int(size[0]), int(size[1])
        except (TypeError, ValueError, IndexError):
            width, height = DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT
        self.resize(max(400, width), max(300, height))

        # Always open centered, regardless of where the user moved it.
        screen = QApplication.primaryScreen()
        if screen is not None:
            frame = self.frameGeometry()
            frame.moveCenter(screen.availableGeometry().center())
            self.move(frame.topLeft())

        if self.user_settings.get("window_maximized", False):
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def _collect_settings(self) -> dict:
        if self.isMaximized():
            normal = self.normalGeometry()
            window_size = [normal.width(), normal.height()]
        else:
            window_size = [self.width(), self.height()]
        return {
            "api_key": self.field_apikey.text(),
            "steam_id": self.field_userid.text(),
            "save_data": self.checkbox_save_data.isChecked(),
            "create_name_file": self.checkbox_create_name_file.isChecked(),
            "ignore_unplayed": self.checkbox_ignore_unplayed.isChecked(),
            "achievements_cache_ttl": self.user_settings.get("achievements_cache_ttl", 60),
            "window_size": window_size,
            "window_maximized": self.isMaximized(),
        }

    def _set_status(self, message: str, error: bool = False, html: bool = False) -> None:
        self.status_label.setTextFormat(Qt.RichText if html else Qt.PlainText)
        self.status_label.setText(message)
        self.status_label.setProperty("role", "status_error" if error else "status_success")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _notify_error(self, message: str) -> None:
        """Erro reportado nas 3 camadas: status, som e popup."""
        self._set_status(message, error=True)
        sounds.play_error()
        QMessageBox.warning(self, APP_TITLE, message)

    def closeEvent(self, event) -> None:  # noqa: N802
        settings.save_settings(self._collect_settings())

        # Ask the threads to stop before waiting on them, so a running
        # QThread is never destroyed while still executing.
        for worker in self._cover_workers:
            worker.stop()
        self._batch_runner.close()

        for thread in list(self._cover_workers):
            if thread.isRunning():
                thread.wait(3000)
        if self._owned_games_worker is not None and self._owned_games_worker.isRunning():
            self._owned_games_worker.wait(3000)
        self._batch_runner.wait(3000)

        super().closeEvent(event)
