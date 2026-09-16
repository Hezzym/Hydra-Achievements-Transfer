"""
A small section that lists the currently selected games.

Selections can be hidden by a search, so this panel gives a visible summary
of everything selected and lets you remove items one by one or clear the
whole selection.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

CHIP_MAX_TEXT_WIDTH = 170


class _Chip(QFrame):
    removed = Signal(str)

    def __init__(self, appid: str, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SelectedChip")
        self.setToolTip(f"{name} ({appid})")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(4)

        label = QLabel()
        label.setProperty("role", "chip")
        label.setText(
            label.fontMetrics().elidedText(name, Qt.ElideMiddle, CHIP_MAX_TEXT_WIDTH)
        )

        remove = QToolButton()
        remove.setObjectName("ChipRemove")
        remove.setText("\u00d7")  # multiplication sign (an "x")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip("Remove from selection")
        remove.clicked.connect(lambda: self.removed.emit(appid))

        layout.addWidget(label)
        layout.addWidget(remove)


class SelectedPanel(QWidget):
    remove_requested = Signal(str)
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SelectedPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.title = QLabel("Selected (0)")
        self.title.setProperty("role", "section_title")
        self.clear_button = QPushButton("Clear selection")
        self.clear_button.setProperty("role", "secondary")
        self.clear_button.clicked.connect(self.clear_requested)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.clear_button)
        layout.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("SelectedScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(40)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._chips = QWidget()
        self._chips.setObjectName("SelectedChips")
        self._chips_layout = QHBoxLayout(self._chips)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(6)
        self._chips_layout.addStretch(1)
        self._scroll.setWidget(self._chips)
        layout.addWidget(self._scroll)

        self.empty_label = QLabel("No games selected.")
        self.empty_label.setProperty("role", "hint")
        layout.addWidget(self.empty_label)

        self._games: list[dict] = []
        self._rebuild()

    def set_selected(self, games: list[dict]) -> None:
        self._games = list(games)
        self._rebuild()

    def _rebuild(self) -> None:
        while self._chips_layout.count() > 1:  # keep the trailing stretch
            item = self._chips_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for game in self._games:
            chip = _Chip(game["appid"], game.get("name", game["appid"]))
            chip.removed.connect(self.remove_requested)
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, chip)

        count = len(self._games)
        self.title.setText(f"Selected ({count})")
        self.clear_button.setVisible(count > 0)
        self._scroll.setVisible(count > 0)
        self.empty_label.setVisible(count == 0)
