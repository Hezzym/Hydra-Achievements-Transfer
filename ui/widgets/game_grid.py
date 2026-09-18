"""
Virtualized cover grid, based on QListView + model/delegate.

Unlike creating one QWidget per game, only the visible items are painted
here, so the UI stays light even with large libraries. Multi-selection
(Ctrl/Shift) is native to QListView and the view reflows the columns by
itself when resized.

A "Load more" button is pinned at the bottom-center of the viewport (with a
reserved strip, so it never covers the cards), instead of being a grid item.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QListView,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
)

CARD_WIDTH = 140
COVER_WIDTH = 126
COVER_HEIGHT = 190
NAME_HEIGHT = 34
PLAYTIME_HEIGHT = 16
LINK_HEIGHT = 16
LINK_MARGIN = 2
NAME_MARGIN = 6
CARD_HEIGHT = (
    8 + COVER_HEIGHT + NAME_MARGIN + NAME_HEIGHT + PLAYTIME_HEIGHT + LINK_MARGIN + LINK_HEIGHT + 8
)

CELL_WIDTH = CARD_WIDTH + 14
CELL_HEIGHT = CARD_HEIGHT + 14

APPID_ROLE = Qt.UserRole + 1
NAME_ROLE = Qt.UserRole + 2
COVER_ROLE = Qt.UserRole + 3
PLAYTIME_ROLE = Qt.UserRole + 4

# Reused as the default `parent` argument (never constructed in the signature).
INVALID_INDEX = QModelIndex()

LINK_TEXT = "Steam achievements"
LOAD_MORE_TEXT = "Load more"
LOAD_MORE_AREA = 52  # strip reserved at the bottom while the button is shown


def _format_playtime(minutes) -> str:
    """Formats playtime in minutes as 'Unavailable', '45 min' or '12.3 h'."""
    try:
        minutes = int(minutes or 0)
    except (TypeError, ValueError):
        minutes = 0
    if minutes <= 0:
        return "Unavailable"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes / 60:.1f} h"


def _make_thumbnail(pixmap: QPixmap) -> QPixmap:
    """
    Pre-scales and crops the cover to the card size, honoring the screen's
    devicePixelRatio. Done once per cover so the delegate does not have to
    rescale on every repaint.
    """
    dpr = 1.0
    app = QApplication.instance()
    if app is not None and app.primaryScreen() is not None:
        dpr = app.primaryScreen().devicePixelRatio()

    target_w = max(1, round(COVER_WIDTH * dpr))
    target_h = max(1, round(COVER_HEIGHT * dpr))
    scaled = pixmap.scaled(
        target_w, target_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
    if scaled.width() > target_w or scaled.height() > target_h:
        x = (scaled.width() - target_w) // 2
        y = (scaled.height() - target_h) // 2
        scaled = scaled.copy(x, y, target_w, target_h)
    scaled.setDevicePixelRatio(dpr)
    return scaled


def _card_rect(cell: QRect) -> QRect:
    """Card rectangle, centered inside the grid cell."""
    x = cell.x() + (cell.width() - CARD_WIDTH) // 2
    y = cell.y() + (cell.height() - CARD_HEIGHT) // 2
    return QRect(x, y, CARD_WIDTH, CARD_HEIGHT)


def link_rect(cell: QRect) -> QRect:
    """Rectangle of the clickable 'Steam achievements' link inside a cell."""
    card = _card_rect(cell)
    top = (
        card.y()
        + 8
        + COVER_HEIGHT
        + NAME_MARGIN
        + NAME_HEIGHT
        + PLAYTIME_HEIGHT
        + LINK_MARGIN
    )
    return QRect(card.x() + 6, top, CARD_WIDTH - 12, LINK_HEIGHT)


class GameListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._games: list[dict] = []
        self._row_by_appid: dict[str, int] = {}
        self._covers: dict[str, QPixmap] = {}

    def rowCount(self, parent=INVALID_INDEX) -> int:
        return 0 if parent.isValid() else len(self._games)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        game = self._games[index.row()]
        if role == NAME_ROLE or role == Qt.DisplayRole:
            return game.get("name", game["appid"])
        if role == APPID_ROLE:
            return game["appid"]
        if role == COVER_ROLE:
            return self._covers.get(game["appid"])
        if role == PLAYTIME_ROLE:
            return _format_playtime(game.get("playtime_forever", 0))
        return None

    def set_games(self, games: list[dict]) -> None:
        self.beginResetModel()
        self._games = list(games)
        self._row_by_appid = {g["appid"]: i for i, g in enumerate(self._games)}
        self._covers = {}
        self.endResetModel()

    def append_games(self, games: list[dict]) -> None:
        if not games:
            return
        start = len(self._games)
        self.beginInsertRows(QModelIndex(), start, start + len(games) - 1)
        for offset, game in enumerate(games):
            self._row_by_appid[game["appid"]] = start + offset
        self._games.extend(games)
        self.endInsertRows()

    def set_cover(self, appid: str, pixmap: QPixmap) -> None:
        row = self._row_by_appid.get(appid)
        if row is None:
            return
        self._covers[appid] = _make_thumbnail(pixmap)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [COVER_ROLE])

    def row_for_appid(self, appid: str) -> int:
        return self._row_by_appid.get(appid, -1)

    def appids(self) -> list[str]:
        """AppIDs of the currently loaded games, in row order."""
        return [game["appid"] for game in self._games]


class GameItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(CELL_WIDTH, CELL_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        card = _card_rect(option.rect)

        selected = bool(option.state & QStyle.State_Selected)
        border_color = QColor("#7c5cff") if selected else QColor("#333333")
        border_width = 2 if selected else 1
        painter.setBrush(QColor("#1e1e1e"))
        painter.setPen(QPen(border_color, border_width))
        painter.drawRoundedRect(card.adjusted(0, 0, -1, -1), 8, 8)

        cover_rect = QRect(
            card.x() + (CARD_WIDTH - COVER_WIDTH) // 2,
            card.y() + 8,
            COVER_WIDTH,
            COVER_HEIGHT,
        )
        cover = index.data(COVER_ROLE)
        if cover is not None and not cover.isNull():
            path = QPainterPath()
            path.addRoundedRect(cover_rect, 4, 4)
            painter.save()
            painter.setClipPath(path)
            # The cover is already pre-scaled/cropped to the card size.
            painter.drawPixmap(cover_rect, cover)
            painter.restore()
        else:
            painter.setBrush(QColor("#262626"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(cover_rect, 4, 4)
            painter.setPen(QColor("#9a9a9a"))
            painter.drawText(cover_rect, Qt.AlignCenter, "...")

        name_rect = QRect(
            card.x() + 6,
            card.y() + 8 + COVER_HEIGHT + NAME_MARGIN,
            CARD_WIDTH - 12,
            NAME_HEIGHT,
        )
        painter.setPen(QColor("#e6e6e6"))
        font = painter.font()
        # Use a pixel size: the stylesheet sets font sizes in pixels, so
        # pointSize() would be -1 and setPointSize() would warn.
        font.setPixelSize(12)
        painter.setFont(font)
        painter.drawText(
            name_rect,
            Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
            index.data(NAME_ROLE) or "",
        )

        # Playtime, always visible below the name.
        playtime_rect = QRect(
            card.x() + 6,
            name_rect.bottom() + 1,
            CARD_WIDTH - 12,
            PLAYTIME_HEIGHT,
        )
        playtime_font = painter.font()
        playtime_font.setPixelSize(10)
        painter.setFont(playtime_font)
        painter.setPen(QColor("#9a9a9a"))
        painter.drawText(
            playtime_rect,
            Qt.AlignHCenter | Qt.AlignTop,
            index.data(PLAYTIME_ROLE) or "",
        )

        # Clickable link to the game's achievements page on Steam.
        link = link_rect(option.rect)
        link_font = painter.font()
        link_font.setPixelSize(10)
        link_font.setUnderline(True)
        painter.setFont(link_font)
        painter.setPen(QColor("#7c5cff"))
        painter.drawText(link, Qt.AlignHCenter | Qt.AlignTop, LINK_TEXT)

        painter.restore()


class GameGrid(QListView):
    link_activated = Signal(str)  # appid
    load_more_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        # MultiSelection: a click toggles an item, no modifier needed.
        self.setSelectionMode(QAbstractItemView.MultiSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setGridSize(QSize(CELL_WIDTH, CELL_HEIGHT))
        self.setModel(GameListModel(self))
        self.setItemDelegate(GameItemDelegate(self))

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # Floating button pinned at the bottom-center of the viewport. It only
        # shows when the list has more games AND the user scrolled to the end.
        self._has_more = False
        self._load_more_shown = False
        self._load_more_button = QPushButton(LOAD_MORE_TEXT, self)
        self._load_more_button.setFixedSize(150, 36)
        self._load_more_button.hide()
        self._load_more_button.clicked.connect(
            lambda: self.load_more_requested.emit()
        )
        self.verticalScrollBar().valueChanged.connect(self._update_load_more_visibility)
        self.verticalScrollBar().rangeChanged.connect(self._update_load_more_visibility)

    def set_games(self, games: list[dict]) -> None:
        self.model().set_games(games)

    def append_games(self, games: list[dict]) -> None:
        self.model().append_games(games)

    def set_cover(self, appid: str, pixmap: QPixmap) -> None:
        self.model().set_cover(appid, pixmap)

    def set_load_more(self, visible: bool) -> None:
        self._has_more = visible
        self._update_load_more_visibility()

    def _update_load_more_visibility(self, *_args) -> None:
        if not self._has_more:
            self._hide_load_more()
            return

        bar = self.verticalScrollBar()
        if self._load_more_shown:
            # While shown, keep it until the user scrolls up past the strip.
            # (The strip itself grows maximum(), so this hysteresis avoids
            # flicker between show/hide.)
            if bar.value() < bar.maximum() - LOAD_MORE_AREA:
                self._hide_load_more()
            else:
                self._position_load_more()
        elif bar.value() >= bar.maximum():
            self._show_load_more()

    def _show_load_more(self) -> None:
        self._load_more_shown = True
        # Reserve a strip at the bottom so the button never covers a card.
        self.setViewportMargins(0, 0, 0, LOAD_MORE_AREA)
        self._load_more_button.show()
        self._position_load_more()
        self._load_more_button.raise_()

    def _hide_load_more(self) -> None:
        if not self._load_more_shown and self._load_more_button.isHidden():
            return
        self._load_more_shown = False
        self._load_more_button.hide()
        self.setViewportMargins(0, 0, 0, 0)

    def _position_load_more(self) -> None:
        if self._load_more_button.isHidden():
            return
        viewport = self.viewport().geometry()
        button = self._load_more_button
        x = viewport.x() + (viewport.width() - button.width()) // 2
        y = self.height() - LOAD_MORE_AREA + (LOAD_MORE_AREA - button.height()) // 2
        button.move(max(0, x), max(0, y))

    def resizeEvent(self, event):  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._update_load_more_visibility()

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if index.isValid() and link_rect(self.visualRect(index)).contains(pos):
            self.link_activated.emit(self.model().data(index, APPID_ROLE))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802 (Qt naming)
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        over_link = index.isValid() and link_rect(self.visualRect(index)).contains(pos)
        self.viewport().setCursor(Qt.PointingHandCursor if over_link else Qt.ArrowCursor)
        super().mouseMoveEvent(event)
