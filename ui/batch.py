"""Achievement fetch/transfer batch mixin for the main window."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from core import appid_log, cache, settings
from ui import labels, sounds
from ui.helpers import APP_TITLE, parse_appids
from ui.theme import COLOR_ERROR, COLOR_SUCCESS
from ui.workers import OwnedGamesWorker


class BatchMixin:
    def _on_fetch_owned_games_clicked(self) -> None:
        api_key = self.field_apikey.text()
        steam_id = self.field_userid.text()
        if not api_key or not steam_id:
            self._notify_error("Please fill in App ID, API Key and SteamID.")
            return

        cache.clear_achievements_cache()

        # A fresh fetch rebuilds the whole list, so a batch interrupted earlier
        # no longer makes sense to resume: clear it completely.
        self._pending_appids = []
        self._update_resume_button()

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

        # Additional system-tray notification, only when the window is
        # minimized or in the background. The popup below is kept unchanged.
        if self._is_in_background():
            notify_parts: list[str] = []
            if canceled:
                notify_parts.append("Canceled.")
            if failed:
                notify_parts.append(f"{failed} game(s) failed.")
            notify_parts.append(saved_line)
            self._show_notification("\n".join(notify_parts))

        if severity == "error":
            sounds.play_error()
            QMessageBox.critical(self, APP_TITLE, popup_text)
        elif severity == "warning":
            sounds.play_info()
            QMessageBox.warning(self, APP_TITLE, popup_text)
        else:
            sounds.play_success()
            QMessageBox.information(self, APP_TITLE, popup_text)
