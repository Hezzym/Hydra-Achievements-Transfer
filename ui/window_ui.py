"""Menu and layout construction mixin for the main window."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenuBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.constants import APIKEY_URL, STEAMDB_URL, STEAMID_URL
from ui import labels
from ui.helpers import SEARCH_DEBOUNCE_MS
from ui.widgets.field_with_link import ComboFieldWithLink, FieldWithLink
from ui.widgets.game_grid import GameGrid
from ui.widgets.help_hint import HelpHint
from ui.widgets.icons import _make_clear_icon, _separator
from ui.widgets.selected_panel import SelectedPanel


class WindowUIMixin:
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
