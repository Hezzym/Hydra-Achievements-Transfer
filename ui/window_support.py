"""Window lifecycle, settings windows, status, tray and notification mixin."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from core import cache, settings, steam_paths
from core.constants import READ_BEFORE_USE_URL
from ui import labels, sounds
from ui.about_window import AboutWindow
from ui.backup_window import BackupWindow
from ui.helpers import APP_TITLE, DEFAULT_WINDOW_HEIGHT, DEFAULT_WINDOW_WIDTH
from ui.settings_window import SettingsWindow


class WindowSupportMixin:
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

    def _open_backup_window(self) -> None:
        if self._backup_window is None:
            self._backup_window = BackupWindow(parent=self)
        self._backup_window.show()
        self._backup_window.raise_()
        self._backup_window.activateWindow()

    def _open_about_window(self) -> None:
        if self._about_window is None:
            self._about_window = AboutWindow(parent=self)
        self._about_window.show()
        self._about_window.raise_()
        self._about_window.activateWindow()

    def _open_read_before_use(self) -> None:
        QDesktopServices.openUrl(QUrl(READ_BEFORE_USE_URL))

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

    def _setup_tray(self) -> None:
        """Create the tray icon used for background notifications, if available."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(QApplication.windowIcon(), self)
        self._tray.setToolTip(APP_TITLE)
        self._tray.show()

    def _is_in_background(self) -> bool:
        """True when the user is not looking at the window (minimized/unfocused)."""
        if self.isMinimized():
            return True
        return QGuiApplication.applicationState() != Qt.ApplicationActive

    def _show_notification(self, message: str) -> None:
        """Send the batch result to the system tray, flashing the taskbar as fallback."""
        if self._tray is not None and self._tray.isVisible():
            self._tray.showMessage(APP_TITLE, message, QSystemTrayIcon.Information, 5000)
        else:
            QApplication.alert(self, 0)

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
