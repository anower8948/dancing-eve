"""Window flags and placement for the floating companion (transparency, always-on-top,
click-through, keeping the window on a visible screen)."""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QWidget

from eve.desktop.platform_capabilities import DesktopCapabilities


def base_flags() -> Qt.WindowType:
    flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
    # Tool windows stay out of the Windows taskbar / Linux task list.
    flags |= Qt.WindowType.Tool
    return flags


def configure_transparency(widget: QWidget) -> None:
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    if sys.platform == "darwin":
        # Without this, macOS hides Qt.Tool windows whenever another app is active.
        widget.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)


def apply_window_flags(widget: QWidget, caps: DesktopCapabilities, always_on_top: bool, click_through: bool) -> None:
    """Changing flags re-creates the native window, so the widget is re-shown."""
    flags = base_flags()
    if always_on_top and caps.always_on_top:
        flags |= Qt.WindowType.WindowStaysOnTopHint
    if click_through and caps.click_through:
        flags |= Qt.WindowType.WindowTransparentForInput
    if widget.windowFlags() == flags:
        return
    visible = widget.isVisible()
    position = widget.pos()
    widget.setWindowFlags(flags)
    widget.move(position)
    if visible:
        widget.show()


def screen_for_point(point: QPoint) -> QScreen | None:
    for screen in QGuiApplication.screens():
        if screen.availableGeometry().contains(point):
            return screen
    return None


def initial_position(size: tuple[int, int], saved: tuple[int | None, int | None]) -> QPoint:
    """Restore the saved position if it is still on a connected screen, else bottom-right."""
    w, h = size
    x, y = saved
    if x is not None and y is not None:
        center = QPoint(x + w // 2, y + h // 2)
        if screen_for_point(center) is not None:
            return QPoint(x, y)
    screen = QGuiApplication.primaryScreen()
    area: QRect = screen.availableGeometry() if screen else QRect(0, 0, 1280, 800)
    return QPoint(area.right() - w - 40, area.bottom() - h - 40)


def clamp_to_screen(rect: QRect) -> QPoint:
    """Keep at least part of the window reachable after a monitor disappears."""
    screen = screen_for_point(rect.center()) or QGuiApplication.primaryScreen()
    if screen is None:
        return rect.topLeft()
    area = screen.availableGeometry()
    x = min(max(rect.x(), area.left() - rect.width() // 2), area.right() - rect.width() // 2)
    y = min(max(rect.y(), area.top()), area.bottom() - rect.height() // 2)
    return QPoint(x, y)
