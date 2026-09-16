"""
Dev-only script that generates the trophy application icon.

It draws a trophy with QPainter and writes:
    assets/icon.png  (256x256, transparent background)
    assets/icon.ico  (multi-size, for the Windows .exe)

Run it with an offscreen platform so it works without a display:

    set QT_QPA_PLATFORM=offscreen
    python tools/generate_icon.py
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)

OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

BASE_SIZE = 256
ICO_SIZES = [16, 32, 48, 64, 128, 256]

GOLD = QColor("#F3C43B")
GOLD_LIGHT = QColor("#FFE38A")
GOLD_DARK = QColor("#B8860B")
OUTLINE = QColor("#8A5A00")
CREAM = QColor("#FFF0B0")


def _star_path(cx: float, cy: float, outer: float, inner: float) -> QPainterPath:
    path = QPainterPath()
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = outer if i % 2 == 0 else inner
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()
    return path


def draw_trophy(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / BASE_SIZE, size / BASE_SIZE)

    # Handles (drawn first, behind the cup).
    left_handle = QPainterPath()
    left_handle.moveTo(80, 86)
    left_handle.cubicTo(44, 84, 44, 132, 84, 138)
    right_handle = QPainterPath()
    right_handle.moveTo(176, 86)
    right_handle.cubicTo(212, 84, 212, 132, 172, 138)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(OUTLINE, 16, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(left_handle)
    painter.drawPath(right_handle)
    painter.setPen(QPen(GOLD, 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(left_handle)
    painter.drawPath(right_handle)

    # Cup body with a vertical gold gradient.
    body = QPainterPath()
    body.moveTo(78, 70)
    body.lineTo(178, 70)
    body.cubicTo(178, 140, 158, 172, 128, 172)
    body.cubicTo(98, 172, 78, 140, 78, 70)
    body.closeSubpath()
    gradient = QLinearGradient(0, 60, 0, 180)
    gradient.setColorAt(0, GOLD_LIGHT)
    gradient.setColorAt(1, GOLD)
    painter.setBrush(gradient)
    painter.setPen(QPen(OUTLINE, 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.drawPath(body)

    # Rim (top opening).
    painter.setBrush(QColor("#E8B62E"))
    painter.setPen(QPen(OUTLINE, 5))
    painter.drawEllipse(QRectF(76, 60, 104, 22))

    # Star on the cup.
    painter.setBrush(CREAM)
    painter.setPen(QPen(QColor("#A9760A"), 3))
    painter.drawPath(_star_path(128, 116, 26, 11))

    # Stem and base.
    painter.setPen(QPen(OUTLINE, 5))
    painter.setBrush(GOLD)
    painter.drawRoundedRect(QRectF(116, 168, 24, 28), 6, 6)
    painter.drawRoundedRect(QRectF(96, 194, 64, 16), 6, 6)
    painter.drawRoundedRect(QRectF(82, 208, 92, 18), 8, 8)

    painter.end()
    return image


def _png_bytes(image: QImage) -> bytes:
    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.WriteOnly)
    image.save(device, "PNG")
    device.close()
    return bytes(buffer)


def _write_ico(path: Path, pngs: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(pngs))
    entries = b""
    data = b""
    offset = 6 + 16 * len(pngs)
    for size, png in pngs:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset
        )
        data += png
        offset += len(png)
    path.write_bytes(header + entries + data)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pngs = [(size, _png_bytes(draw_trophy(size))) for size in ICO_SIZES]

    png_path = OUT_DIR / "icon.png"
    png_path.write_bytes(dict(pngs)[BASE_SIZE])

    ico_path = OUT_DIR / "icon.ico"
    _write_ico(ico_path, pngs)

    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path}")


if __name__ == "__main__":
    app = QGuiApplication([])
    main()
