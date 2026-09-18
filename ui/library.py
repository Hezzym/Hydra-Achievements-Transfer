"""Game list, cover grid and selection mixin for the main window."""
from __future__ import annotations

from PySide6.QtCore import QItemSelection, QItemSelectionModel, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap

from core import cache
from core.constants import STEAM_ACHIEVEMENTS_URL
from ui import labels
from ui.helpers import PAGE_SIZE, parse_appids
from ui.widgets.game_grid import APPID_ROLE
from ui.workers import CoverDownloadWorker


class LibraryMixin:
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

    def _on_open_steam_link(self, appid: str) -> None:
        steam_id = self.field_userid.text()
        if not steam_id:
            self._notify_error("Fill in the SteamID64 to open the Steam page.")
            return
        url = STEAM_ACHIEVEMENTS_URL.format(steam_id=steam_id, appid=appid)
        QDesktopServices.openUrl(QUrl(url))
