"""
About/credits window.

Opened by the "About" item in the menu bar. Follows the same dark theme
as the rest of the application.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from core.constants import APP_NAME, APP_VERSION, AUTHOR, GITHUB_URL
from ui.theme import DARK_STYLESHEET
from ui.widgets.field_with_link import ClickableLink

WINDOW_TITLE = "About"


class AboutWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(WINDOW_TITLE)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setMinimumWidth(380)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        title = QLabel(APP_NAME)
        title.setProperty("role", "about_title")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(f"Created by {AUTHOR}")
        subtitle.setAlignment(Qt.AlignCenter)

        github_row = QHBoxLayout()
        github_row.setSpacing(6)
        github_row.addStretch(1)
        github_row.addWidget(QLabel("GitHub:"))
        github_row.addWidget(ClickableLink(GITHUB_URL, GITHUB_URL))
        github_row.addStretch(1)

        version = QLabel(f"Version {APP_VERSION}")
        version.setAlignment(Qt.AlignCenter)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(github_row)
        layout.addWidget(version)
        layout.addSpacing(8)
        layout.addWidget(close_button)
