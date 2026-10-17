"""Capture status line (colour dot + label + explanation) and a music activity meter."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from eve.audio.capture_status import CaptureStatus, CaptureStatusInfo
from eve.desktop.system_tray import status_color


class _Dot(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(14, 14)
        self.color = QColor(150, 150, 150)

    def paintEvent(self, _event: QPaintEvent) -> None:  # Qt naming
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(1, 1, 12, 12))
        p.end()


class StatusWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.dot = _Dot()
        self.label = QLabel("Not listening")
        self.label.setObjectName("statusText")
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("hint")
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.dot)
        top.addWidget(self.label, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(self.detail)

    def set_status(self, info: CaptureStatusInfo, listening: bool) -> None:
        status = info.status if listening or info.status.is_failure else CaptureStatus.STOPPED
        self.label.setText(status.label + (f" · {info.source_name}" if info.source_name and status.is_active else ""))
        self.detail.setText(info.message if info.message != status.label else "")
        self.detail.setVisible(bool(self.detail.text()))
        self.dot.color = status_color(status) or QColor(150, 150, 150)
        self.dot.update()


class LevelMeter(QWidget):
    """Horizontal meter; shows real captured level (dBFS mapped to 0..1) and activity."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(10)
        self.setMaximumHeight(10)
        self.level = 0.0
        self.activity = 0.0

    def set_values(self, level: float, activity: float) -> None:
        self.level = max(0.0, min(1.0, level))
        self.activity = max(0.0, min(1.0, activity))
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.palette().mid().color())
        p.drawRoundedRect(rect, 4, 4)
        filled = QRectF(rect)
        filled.setWidth(rect.width() * self.level)
        base = QColor(59, 167, 245)
        p.setBrush(base if self.activity > 0.5 else base.darker(140))
        p.drawRoundedRect(filled, 4, 4)
        p.end()
