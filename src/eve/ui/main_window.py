"""The floating companion window: paints rendered frames, handles drag/click/menu.

It never imports the renderer or audio code — it receives ``FrameImage``s and talks to
the application through ``AppController``.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QContextMenuEvent,
    QImage,
    QKeySequence,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QScreen,
    QShortcut,
    QShowEvent,
    QWheelEvent,
    QWindow,
)
from PySide6.QtWidgets import QMenu, QWidget

from eve.app_context import AppController
from eve.audio.capture_status import CaptureStatus, CaptureStatusInfo
from eve.desktop import window_manager as wm
from eve.desktop.system_tray import status_color
from eve.rendering.render_settings import WINDOW_ASPECT
from eve.rendering.renderer_interface import FrameImage

DRAG_THRESHOLD = 4


class CompanionWindow(QWidget):
    resized = Signal(int, int)  # physical pixel size for the renderer
    moved = Signal(int, int)

    def __init__(self, app: AppController) -> None:
        super().__init__(None, wm.base_flags())
        self.app = app
        self.setWindowTitle("Project EVE")
        wm.configure_transparency(self)
        self._image: QImage | None = None
        self._frame: FrameImage | None = None
        self._status = CaptureStatusInfo(CaptureStatus.STOPPED)
        self._press_pos: QPoint | None = None
        self._press_window_pos: QPoint | None = None
        self._dragging = False
        self._manual_drag = False
        self._listening = False
        self._watched_handle: QWindow | None = None
        self._move_save = QTimer(self)
        self._move_save.setSingleShot(True)
        self._move_save.setInterval(600)
        self._move_save.timeout.connect(self._emit_moved)
        self.set_character_size(app.settings.character_size)
        QShortcut(QKeySequence.StandardKey.Quit, self, app.quit)
        QShortcut(QKeySequence("Ctrl+,"), self, app.show_settings)

    # -- geometry -----------------------------------------------------------------------
    def set_character_size(self, height: int) -> None:
        width = int(round(height * WINDOW_ASPECT))
        center = self.geometry().center() if self.isVisible() else None
        self.setFixedSize(width, height)
        if center is not None:
            self.move(center.x() - width // 2, center.y() - height // 2)
        self._emit_resized()

    def physical_size(self) -> tuple[int, int]:
        ratio = self.devicePixelRatioF()
        return int(round(self.width() * ratio)), int(round(self.height() * ratio))

    def _emit_resized(self) -> None:
        w, h = self.physical_size()
        self.resized.emit(w, h)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        handle = self.windowHandle()
        if handle is not None and handle is not self._watched_handle:
            # Moving between Retina and non-Retina monitors changes the pixel ratio.
            handle.screenChanged.connect(self._on_screen_changed)
            self._watched_handle = handle
        self._emit_resized()

    def _on_screen_changed(self, _screen: QScreen) -> None:
        self._emit_resized()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._move_save.start()

    def _emit_moved(self) -> None:
        pos = self.pos()
        self.moved.emit(pos.x(), pos.y())

    # -- frames & status ------------------------------------------------------------------
    def set_frame(self, frame: FrameImage) -> None:
        self._frame = frame  # keep the buffer alive while QImage references it
        image = QImage(
            frame.pixels.data, frame.width, frame.height, frame.stride, QImage.Format.Format_ARGB32_Premultiplied
        )
        image.setDevicePixelRatio(frame.width / max(1, self.width()))
        self._image = image
        self.update()

    def set_status(self, info: CaptureStatusInfo, listening: bool) -> None:
        self._status = info
        self._listening = listening
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        # One pass: the frame covers the whole window and already carries alpha, so
        # "Source" replaces the previous contents without a separate clear.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        if self._image is not None:
            painter.drawImage(QPointF(0, 0), self._image)
        else:
            painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self._listening:
            self._paint_listening_indicator(painter)
        painter.end()

    def _paint_listening_indicator(self, painter: QPainter) -> None:
        """Visible privacy indicator: a small dot whenever audio capture is active."""
        color = status_color(self._status.status) or QColor(150, 150, 150)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = max(4.0, self.height() * 0.022)
        center = QPointF(self.width() - r * 2.2, r * 2.2)
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
        painter.setBrush(color)
        painter.drawEllipse(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r))

    # -- interaction ----------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._press_window_pos = self.pos()
            self._dragging = False
            self._manual_drag = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_pos is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = event.globalPosition().toPoint() - self._press_pos
        if not self._dragging and delta.manhattanLength() >= DRAG_THRESHOLD:
            self._dragging = True
            handle = self.windowHandle()
            # Native move: smooth, works on Wayland; fall back to manual moving.
            if handle is None or not handle.startSystemMove():
                self._manual_drag = True
        if self._manual_drag and self._press_window_pos is not None:
            self.move(self._press_window_pos + delta)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._dragging and self._press_pos is not None:
                self.app.poke()
            self._press_pos = None
            self._dragging = False
            self._manual_drag = False
            self._move_save.start()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.app.show_settings()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            step = 20 if event.angleDelta().y() > 0 else -20
            self.app.update_setting("character_size", self.app.settings.character_size + step)
            event.accept()
            return
        super().wheelEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        listening = self.app.is_listening()
        status = QAction(self.app.capture_status().status.label, menu)
        status.setEnabled(False)
        menu.addAction(status)
        menu.addSeparator()
        listen = menu.addAction(
            "Stop listening" if listening else "Start listening",
            self.app.stop_listening if listening else self.app.start_listening,
        )
        listen.setEnabled(self.app.can_listen())
        if self.app.capture_status().status.is_failure:
            menu.addAction("Retry audio capture", self.app.retry_capture)
        menu.addSeparator()
        if self.app.capabilities.always_on_top:
            top = menu.addAction("Always on top")
            top.setCheckable(True)
            top.setChecked(self.app.settings.always_on_top)
            top.toggled.connect(lambda on: self.app.update_setting("always_on_top", on))
        if self.app.capabilities.click_through and self.app.capabilities.system_tray:
            menu.addAction(
                "Click-through (re-enable from the tray icon)", lambda: self.app.update_setting("click_through", True)
            )
        if self.app.capabilities.system_tray:
            menu.addAction("Hide (show again from the tray icon)", lambda: self.app.set_companion_visible(False))
        menu.addAction("Settings…", self.app.show_settings)
        menu.addSeparator()
        menu.addAction("Quit Project EVE", self.app.quit)
        menu.exec(event.globalPos())
