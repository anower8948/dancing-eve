"""Procedurally drawn icons (no image assets needed)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap


def robot_pixmap(size: int = 64, status_color: QColor | None = None, template: bool = False) -> QPixmap:
    """A little robot head: white shell, dark visor, two glowing eyes.

    ``template`` draws a monochrome silhouette (macOS menu-bar template image).
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64.0
    shell = QRectF(4 * s, 12 * s, 56 * s, 42 * s)
    visor = QRectF(10 * s, 19 * s, 44 * s, 26 * s)
    if template:
        p.setBrush(QColor(0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(shell, 20 * s, 20 * s)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.drawRoundedRect(QRectF(16 * s, 27 * s, 11 * s, 8 * s), 4 * s, 4 * s)
        p.drawRoundedRect(QRectF(37 * s, 27 * s, 11 * s, 8 * s), 4 * s, 4 * s)
    else:
        p.setPen(QPen(QColor(150, 160, 175), 1.5 * s))
        p.setBrush(QColor(244, 246, 250))
        p.drawRoundedRect(shell, 20 * s, 20 * s)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(12, 14, 22))
        p.drawRoundedRect(visor, 12 * s, 12 * s)
        p.setBrush(QColor(90, 200, 255))
        p.drawRoundedRect(QRectF(17 * s, 27 * s, 10 * s, 8 * s), 4 * s, 4 * s)
        p.drawRoundedRect(QRectF(37 * s, 27 * s, 10 * s, 8 * s), 4 * s, 4 * s)
    if status_color is not None:
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setPen(QPen(QColor(255, 255, 255), 2 * s))
        p.setBrush(QBrush(status_color))
        p.drawEllipse(QRectF(44 * s, 42 * s, 18 * s, 18 * s))
    p.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 64, 128, 256):
        icon.addPixmap(robot_pixmap(size))
    return icon
