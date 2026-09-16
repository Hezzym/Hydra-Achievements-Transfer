"""
Settings window: achievements cache TTL and cache reset.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout

from ui import labels
from ui.theme import DARK_STYLESHEET


class SettingsWindow(QDialog):
    ttl_changed = Signal(int)  # minutes
    reset_requested = Signal()

    def __init__(self, ttl_minutes: int, parent=None):
        super().__init__(parent)

        self.setWindowTitle(labels.SETTINGS_TITLE)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel(labels.SETTINGS_CACHE_TTL)
        title.setProperty("role", "section_title")
        layout.addWidget(title)

        description = QLabel(labels.SETTINGS_CACHE_TTL_DESCRIPTION)
        description.setWordWrap(True)
        layout.addWidget(description)

        row = QHBoxLayout()
        self.spin = QSpinBox()
        self.spin.setRange(0, 100000)
        self.spin.setValue(max(0, int(ttl_minutes)))
        self.spin.setSuffix(labels.SETTINGS_MINUTES_SUFFIX)
        self.spin.valueChanged.connect(self.ttl_changed)
        row.addWidget(self.spin)
        row.addStretch(1)
        layout.addLayout(row)

        reset_button = QPushButton(labels.SETTINGS_RESET_CACHE)
        reset_button.setProperty("role", "secondary")
        reset_button.clicked.connect(self.reset_requested)
        layout.addWidget(reset_button)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("role", "hint")
        layout.addWidget(self.status_label)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)
