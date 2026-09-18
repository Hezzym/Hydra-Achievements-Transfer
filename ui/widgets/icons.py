"""Small procedurally-drawn icons and separators used by the UI."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel


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
