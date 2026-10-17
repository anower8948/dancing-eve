"""Settings window: listening controls/status, dance options, window options, debug."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from eve import APP_NAME, __version__
from eve.app_context import AppController
from eve.audio.capture_status import CaptureStatus, CaptureStatusInfo
from eve.config import LIMITS
from eve.dance.movement_library import DANCE_STYLES
from eve.ui.debug_panel import DebugPanel
from eve.ui.status_widget import LevelMeter, StatusWidget
from eve.ui.styles import SETTINGS_QSS


def _slider(lo: float, hi: float, value: float, scale: float = 100.0) -> QSlider:
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(int(lo * scale), int(hi * scale))
    slider.setValue(int(value * scale))
    return slider


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


class SettingsWindow(QWidget):
    def __init__(self, app: AppController, renderer_info: str = "") -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.app = app
        self.setWindowTitle(f"{APP_NAME} — Settings")
        self.setObjectName("settingsRoot")
        self.setStyleSheet(SETTINGS_QSS)
        self.setMinimumWidth(420)
        s = app.settings
        caps = app.capabilities

        # --- Listening -----------------------------------------------------------------
        self.status = StatusWidget()
        self.meter = LevelMeter()
        self.listen_button = QPushButton()
        self.listen_button.setObjectName("primary")
        self.listen_button.clicked.connect(self._toggle_listening)
        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(app.retry_capture)
        self.privacy_button = QPushButton("Open Privacy Settings…")
        self.privacy_button.clicked.connect(app.open_privacy_settings)
        self.privacy_button.setVisible(False)
        self.source = QComboBox()
        self.source.currentIndexChanged.connect(self._source_changed)
        refresh_sources = QPushButton("↻")
        refresh_sources.setToolTip("Refresh audio sources")
        refresh_sources.setFixedWidth(34)
        refresh_sources.clicked.connect(lambda: self._load_sources(refresh=True))
        buttons = QHBoxLayout()
        buttons.addWidget(self.listen_button)
        buttons.addWidget(self.retry_button)
        buttons.addWidget(self.privacy_button)
        buttons.addStretch(1)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source, 1)
        source_row.addWidget(refresh_sources)
        listen_box = QGroupBox("Listening")
        lb = QVBoxLayout(listen_box)
        lb.addWidget(self.status)
        lb.addWidget(QLabel("Music activity"))
        lb.addWidget(self.meter)
        lb.addLayout(source_row)
        lb.addLayout(buttons)
        lb.addWidget(_hint("Audio is analysed on this computer only. Nothing is recorded, stored or uploaded."))

        # --- Dance ---------------------------------------------------------------------
        dance_box = QGroupBox("Dancing")
        df = QFormLayout(dance_box)
        df.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.sensitivity = _slider(*LIMITS["sensitivity"], s.sensitivity)
        self.sensitivity.valueChanged.connect(lambda v: app.update_setting("sensitivity", v / 100.0))
        self.intensity = _slider(*LIMITS["dance_intensity"], s.dance_intensity)
        self.intensity.valueChanged.connect(lambda v: app.update_setting("dance_intensity", v / 100.0))
        self.reduced = QCheckBox("Reduced motion (smaller, calmer movements, no spins)")
        self.reduced.setChecked(s.reduced_motion)
        self.reduced.toggled.connect(lambda on: app.update_setting("reduced_motion", on))
        self.style_box = QComboBox()
        for key, label in DANCE_STYLES.items():
            self.style_box.addItem(label, key)
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(s.dance_style)))
        self.style_box.currentIndexChanged.connect(
            lambda _i: app.update_setting("dance_style", self.style_box.currentData())
        )
        df.addRow("Audio sensitivity", self.sensitivity)
        df.addRow("Dance intensity", self.intensity)
        df.addRow("Dance style", self.style_box)
        df.addRow(self.reduced)

        # --- Window --------------------------------------------------------------------
        window_box = QGroupBox("Window")
        wf = QFormLayout(window_box)
        wf.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.size_slider = _slider(*LIMITS["character_size"], s.character_size, scale=1.0)
        self.size_slider.valueChanged.connect(lambda v: app.update_setting("character_size", v))
        wf.addRow("Character size", self.size_slider)
        self.on_top = QCheckBox("Always on top")
        self.on_top.setChecked(s.always_on_top)
        self.on_top.setEnabled(caps.always_on_top)
        self.on_top.toggled.connect(lambda on: app.update_setting("always_on_top", on))
        wf.addRow(self.on_top)
        self.click_through = QCheckBox("Click-through (EVE ignores the mouse)")
        self.click_through.setChecked(s.click_through)
        self.click_through.setEnabled(caps.click_through and caps.system_tray)
        self.click_through.toggled.connect(lambda on: app.update_setting("click_through", on))
        wf.addRow(self.click_through)
        if caps.click_through and caps.system_tray:
            wf.addRow(_hint("Turn click-through off again from the tray / menu-bar icon or this window."))
        elif caps.click_through:
            wf.addRow(_hint("Click-through needs a tray icon to switch it off again, and no tray is available."))
        self.power = QCheckBox("Power saving (30 FPS)")
        self.power.setChecked(s.power_saving)
        self.power.toggled.connect(lambda on: app.update_setting("power_saving", on))
        wf.addRow(self.power)
        self.shadow = QCheckBox("Floor shadow")
        self.shadow.setChecked(s.show_shadow)
        self.shadow.toggled.connect(lambda on: app.update_setting("show_shadow", on))
        wf.addRow(self.shadow)
        self.tray = QCheckBox("Show tray / menu-bar icon")
        self.tray.setChecked(s.show_tray_icon)
        self.tray.setEnabled(caps.system_tray)
        self.tray.toggled.connect(lambda on: app.update_setting("show_tray_icon", on))
        wf.addRow(self.tray)
        for note in caps.notes:
            wf.addRow(_hint(note))

        # --- Advanced ------------------------------------------------------------------
        adv_box = QGroupBox("Advanced")
        av = QVBoxLayout(adv_box)
        self.debug = QCheckBox("Show debug panel")
        self.debug.setChecked(s.debug_mode)
        self.debug.toggled.connect(self._debug_toggled)
        av.addWidget(self.debug)
        self.debug_panel = DebugPanel(app)
        self.debug_panel.setVisible(s.debug_mode)
        av.addWidget(self.debug_panel)
        row = QHBoxLayout()
        logs = QPushButton("Open log folder")
        logs.clicked.connect(app.open_log_folder)
        reset = QPushButton("Reset preferences…")
        reset.setObjectName("danger")
        reset.clicked.connect(self._reset)
        row.addWidget(logs)
        row.addWidget(reset)
        row.addStretch(1)
        av.addLayout(row)
        av.addWidget(_hint(f"{APP_NAME} {__version__} · Python {sys.version.split()[0]} · {renderer_info}"))

        # --- Footer --------------------------------------------------------------------
        footer = QHBoxLayout()
        self.visible_button = QPushButton()
        self.visible_button.clicked.connect(self._toggle_companion)
        quit_button = QPushButton("Quit Project EVE")
        quit_button.clicked.connect(app.quit)
        footer.addWidget(self.visible_button)
        footer.addStretch(1)
        footer.addWidget(quit_button)

        content = QWidget()
        content.setObjectName("settingsRoot")
        layout = QVBoxLayout(content)
        for box in (listen_box, dance_box, window_box, adv_box):
            layout.addWidget(box)
        layout.addLayout(footer)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.resize(460, 760)

        self._loading_sources = False
        self._load_sources()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick)
        self.refresh()

    # -- behaviour ------------------------------------------------------------------------
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._timer.start()
        self.refresh()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self) -> None:
        f = self.app.latest_features()
        self.meter.set_values(self.app.audio_level(), f.music_activity)
        if self.debug_panel.isVisible():
            self.debug_panel.refresh()

    def _toggle_companion(self) -> None:
        self.app.set_companion_visible(not self.app.companion_visible())
        self.refresh()

    def _toggle_listening(self) -> None:
        if self.app.is_listening():
            self.app.stop_listening()
        else:
            self.app.start_listening()
        self.refresh()

    def _debug_toggled(self, on: bool) -> None:
        self.app.update_setting("debug_mode", on)
        self.debug_panel.setVisible(on)

    def _load_sources(self, refresh: bool = False) -> None:
        self._loading_sources = True
        self.source.clear()
        self.source.addItem("Automatic (system output)", None)
        for src in self.app.audio_sources(refresh=refresh):
            self.source.addItem(src.name + (" (default)" if src.is_default else ""), src.id)
        index = self.source.findData(self.app.settings.audio_source_id)
        self.source.setCurrentIndex(max(0, index))
        self._loading_sources = False

    def _source_changed(self, _index: int) -> None:
        if not self._loading_sources:
            self.app.set_audio_source(self.source.currentData())

    def _reset(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reset preferences",
            "Restore all settings to their defaults? (Your current settings file is kept as a backup.)",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.app.reset_settings()

    def sync_from_settings(self) -> None:
        """Re-read every control from the settings (after a reset or tray change)."""
        s = self.app.settings
        pairs = (
            (self.sensitivity, int(s.sensitivity * 100)),
            (self.intensity, int(s.dance_intensity * 100)),
            (self.size_slider, s.character_size),
        )
        self.style_box.blockSignals(True)
        self.style_box.setCurrentIndex(max(0, self.style_box.findData(s.dance_style)))
        self.style_box.blockSignals(False)
        for slider, value in pairs:
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        for box, value in (
            (self.reduced, s.reduced_motion),
            (self.on_top, s.always_on_top),
            (self.click_through, s.click_through),
            (self.power, s.power_saving),
            (self.shadow, s.show_shadow),
            (self.tray, s.show_tray_icon),
            (self.debug, s.debug_mode),
        ):
            box.blockSignals(True)
            box.setChecked(value)
            box.blockSignals(False)
        self.debug_panel.setVisible(s.debug_mode)
        self._load_sources()
        self.refresh()

    def update_status(self, info: CaptureStatusInfo) -> None:
        listening = self.app.is_listening()
        self.status.set_status(info, listening)
        self.retry_button.setVisible(info.status.is_failure)
        self.privacy_button.setVisible(info.status == CaptureStatus.PERMISSION_DENIED and sys.platform == "darwin")
        self.listen_button.setText("Stop listening" if listening else "Start listening")
        self.listen_button.setEnabled(self.app.can_listen())
        self.source.setEnabled(self.app.can_listen())

    def refresh(self) -> None:
        self.update_status(self.app.capture_status())
        self.visible_button.setText("Hide EVE" if self.app.companion_visible() else "Show EVE")
