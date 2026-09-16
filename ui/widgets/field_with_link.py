"""
Composite widget: label + text field (or editable combo) + clickable link
that opens a reference URL (e.g. SteamDB, steamid.io...).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget


class ClickableLink(QLabel):
    def __init__(self, text: str, url: str, parent=None):
        super().__init__(text, parent)
        self._url = url
        self.setProperty("role", "link")
        self.setCursor(Qt.PointingHandCursor)

    def set_url(self, url: str) -> None:
        self._url = url

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class FieldWithLink(QWidget):
    """Label on top, QLineEdit in the middle, clickable link below."""

    def __init__(self, label_text: str, link_text: str, url: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.label = QLabel(label_text)
        self.input = QLineEdit()
        self.link = ClickableLink(link_text, url)

        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.link)

    def text(self) -> str:
        return self.input.text().strip()

    def set_text(self, value: str) -> None:
        self.input.setText(value)


class ComboFieldWithLink(QWidget):
    """
    Like FieldWithLink, but with an editable QComboBox instead of the
    QLineEdit (used for the SteamID field, which can be picked from a list
    of local accounts or typed manually).

    Explicitly tracks whether the current value came from a list selection
    (uses the raw SteamID stored in userData) or was typed manually (uses
    the text exactly as typed) -- it does not rely on Qt's automatic
    currentIndex behavior, which only applies to interactive editing and
    not to programmatic calls such as setCurrentText().
    """

    def __init__(self, label_text: str, link_text: str, url: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._manual_entry = True  # True = usar o texto digitado; False = usar userData

        self.label = QLabel(label_text)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.activated.connect(self._on_item_activated)
        self.combo.lineEdit().textEdited.connect(self._on_text_edited_by_user)
        self.link = ClickableLink(link_text, url)

        layout.addWidget(self.label)
        layout.addWidget(self.combo)
        layout.addWidget(self.link)

    def _on_item_activated(self, index: int) -> None:
        self._manual_entry = False

    def _on_text_edited_by_user(self, _text: str) -> None:
        self._manual_entry = True

    def text(self) -> str:
        if not self._manual_entry:
            data = self.combo.currentData()
            if data is not None:
                return str(data).strip()
        return self.combo.currentText().strip()

    def set_text(self, value: str) -> None:
        """Sets the value programmatically (e.g. restoring saved settings)."""
        for i in range(self.combo.count()):
            if str(self.combo.itemData(i)) == value:
                self.combo.setCurrentIndex(i)
                self._manual_entry = False
                return
        self._manual_entry = True
        self.combo.setCurrentIndex(-1)
        self.combo.setEditText(value)

    def set_options(self, options: list[tuple[str, str]]) -> None:
        """options: list of (internal_value, display_text)."""
        previous_value = self.text() if not self._manual_entry or self.combo.count() == 0 else None

        self.combo.blockSignals(True)
        self.combo.clear()
        for value, display in options:
            self.combo.addItem(display, userData=value)
        # addItem() on a previously empty list makes Qt auto-select index 0
        # without firing 'activated' -- without this explicit reset the field
        # would keep showing "Name (steamid)" by default and text() would read
        # the whole string instead of the raw steamid.
        self.combo.setCurrentIndex(-1)
        self.combo.clearEditText()
        self.combo.blockSignals(False)
        self._manual_entry = True

        if previous_value:
            self.set_text(previous_value)
