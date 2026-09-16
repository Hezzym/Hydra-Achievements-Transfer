"""
A small "(?)" hint shown next to a UI option. It displays an explanation
in a popup when clicked and also as a tooltip on hover.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox


class HelpHint(QLabel):
    def __init__(self, title: str, message: str, parent=None):
        super().__init__("(?)", parent)
        self._title = title
        self._message = message

        self.setProperty("role", "help")
        self.setCursor(Qt.WhatsThisCursor)
        self.setToolTip(message)

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        QMessageBox.information(self, self._title, self._message)
        super().mousePressEvent(event)
