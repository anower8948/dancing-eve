"""System tray / menu-bar icon: the always-available way to control (and regain) EVE,
including when click-through mode makes the robot ignore the mouse."""

from __future__ import annotations

import sys

from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from eve.app_context import AppController
from eve.audio.capture_status import CaptureStatus, CaptureStatusInfo
from eve.desktop.icons import robot_pixmap

STATUS_COLORS = {
    CaptureStatus.RECEIVING_AUDIO: QColor(52, 199, 89),
    CaptureStatus.NO_AUDIO_DETECTED: QColor(255, 179, 64),
    CaptureStatus.CONNECTING: QColor(255, 179, 64),
    CaptureStatus.WAITING_FOR_PERMISSION: QColor(255, 179, 64),
}
FAILURE_COLOR = QColor(255, 69, 58)


def status_color(status: CaptureStatus) -> QColor | None:
    if status.is_failure:
        return FAILURE_COLOR
    return STATUS_COLORS.get(status)


class SystemTray:
    def __init__(self, app: AppController) -> None:
        self.app = app
        self.icon = QSystemTrayIcon()
        self.menu = QMenu()
        self._status_action = QAction("Not listening", self.menu)
        self._status_action.setEnabled(False)
        self._listen_action = QAction("Start listening", self.menu)
        self._listen_action.triggered.connect(self._toggle_listening)
        self._retry_action = QAction("Retry audio capture", self.menu)
        self._retry_action.triggered.connect(app.retry_capture)
        self._show_action = QAction("Hide EVE", self.menu)
        self._show_action.triggered.connect(self._toggle_visible)
        self._click_action = QAction("Click-through (ignore mouse)", self.menu)
        self._click_action.setCheckable(True)
        self._click_action.toggled.connect(lambda on: app.update_setting("click_through", on))
        self._top_action = QAction("Always on top", self.menu)
        self._top_action.setCheckable(True)
        self._top_action.toggled.connect(lambda on: app.update_setting("always_on_top", on))
        settings_action = QAction("Settings…", self.menu)
        settings_action.triggered.connect(app.show_settings)
        quit_action = QAction("Quit Project EVE", self.menu)
        quit_action.triggered.connect(app.quit)
        for item in (
            self._status_action,
            None,
            self._listen_action,
            self._retry_action,
            None,
            self._show_action,
            self._click_action,
            self._top_action,
            None,
            settings_action,
            None,
            quit_action,
        ):
            if item is None:
                self.menu.addSeparator()
            else:
                self.menu.addAction(item)
        self._click_action.setVisible(app.capabilities.click_through)
        self._top_action.setVisible(app.capabilities.always_on_top)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self._last_color: QColor | None = None
        self._set_icon(None)
        self.refresh()

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def _set_icon(self, color: QColor | None) -> None:
        if sys.platform == "darwin" and color is None:
            icon = QIcon(robot_pixmap(44, template=True))
            icon.setIsMask(True)  # adapts to light/dark menu bar
        else:
            icon = QIcon(robot_pixmap(44, color))
        self.icon.setIcon(icon)

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if sys.platform != "darwin" and reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.app.show_settings()

    def _toggle_listening(self) -> None:
        if self.app.is_listening():
            self.app.stop_listening()
        else:
            self.app.start_listening()

    def _toggle_visible(self) -> None:
        self.app.set_companion_visible(not self.app.companion_visible())
        self.refresh()

    def update_status(self, info: CaptureStatusInfo) -> None:
        self._status_action.setText(info.status.label)
        self.icon.setToolTip(f"Project EVE — {info.text}")
        color = status_color(info.status) if self.app.is_listening() else None
        if color != self._last_color:
            self._last_color = color
            self._set_icon(color)
        self.refresh()

    def refresh(self) -> None:
        settings = self.app.settings
        self._listen_action.setText("Stop listening" if self.app.is_listening() else "Start listening")
        self._listen_action.setEnabled(self.app.can_listen())
        self._retry_action.setVisible(self.app.capture_status().status.is_failure)
        self._show_action.setText("Hide EVE" if self.app.companion_visible() else "Show EVE")
        for action, value in ((self._click_action, settings.click_through), (self._top_action, settings.always_on_top)):
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)
