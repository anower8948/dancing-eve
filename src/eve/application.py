"""Composition root: wires capture → analysis → dance → animation → renderer → window.

Threading model:
  * capture backend thread / OS callback queue  → SampleBuffer (bounded)
  * analyzer worker thread                       → latest AudioFeatures + bounded event queue
  * Qt main thread: frame timer (dance, animation, Panda3D render, paint) and a 4 Hz
    status timer (capture status, UI refresh). Nothing on the main thread blocks on audio.
"""

from __future__ import annotations

import logging
import math
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from eve import APP_NAME
from eve.animation.animation_controller import AnimationController
from eve.audio.analyzer import AnalyzerWorker
from eve.audio.audio_features import SILENT_FEATURES, AudioFeatures
from eve.audio.capture_interface import AudioSource
from eve.audio.capture_manager import CaptureManager
from eve.audio.capture_status import CaptureStatus, CaptureStatusInfo
from eve.audio.sample_buffer import SampleBuffer
from eve.config import Settings, validate
from eve.constants import IDLE_FPS, IDLE_POWER_SAVE_AFTER, STATUS_POLL_MS
from eve.core.lifecycle import ShutdownSequence
from eve.dance.dance_controller import DanceController, DanceOutput, DanceSettings
from eve.dance.dance_state import DanceState
from eve.dance.demo_source import DemoMusicSource
from eve.desktop import window_manager as wm
from eve.desktop.icons import app_icon
from eve.desktop.platform_capabilities import detect_capabilities
from eve.desktop.system_tray import SystemTray
from eve.exceptions import RendererUnavailable
from eve.rendering.panda3d_renderer import Panda3DRenderer
from eve.rendering.render_settings import RenderSettings
from eve.rendering.renderer_interface import FrameImage
from eve.storage.paths import AppPaths
from eve.storage.settings_store import SettingsStore
from eve.ui.main_window import CompanionWindow
from eve.ui.settings_window import SettingsWindow

log = logging.getLogger(__name__)

PRIVACY_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


@dataclass
class AppOptions:
    demo: bool = False
    no_audio: bool = False
    debug: bool = False
    smoke_test: float = 0.0  # run N seconds, print a performance report, quit
    screenshot: str | None = None  # save the last frame here when quitting (smoke test)
    size: int | None = None  # --size: this run only, never saved
    fps: int | None = None  # --fps: this run only, never saved


class EveApplication(QObject):
    def __init__(
        self, qapp: QApplication, options: AppOptions, paths: AppPaths, store: SettingsStore, settings: Settings
    ) -> None:
        super().__init__()
        self.qapp = qapp
        self.options = options
        self.paths = paths
        self.store = store
        self.settings = settings
        self.capabilities = detect_capabilities(qapp.platformName(), QSystemTrayIcon.isSystemTrayAvailable())
        caps = self.capabilities
        if settings.click_through and not (caps.click_through and caps.system_tray and settings.show_tray_icon):
            settings.click_through = False  # never trap the user behind an unclickable window
        qapp.setWindowIcon(app_icon())

        self.buffer = SampleBuffer()
        self.capture: CaptureManager | None = None
        if not (options.no_audio or options.demo):
            self.capture = CaptureManager(self.buffer)
        self.worker = AnalyzerWorker(self.buffer, settings.sensitivity)
        self.demo = DemoMusicSource() if options.demo else None
        self.dance = DanceController(DanceSettings(settings.dance_intensity, settings.reduced_motion))
        self.animation = AnimationController(reduced_motion=settings.reduced_motion)
        self.renderer = Panda3DRenderer(RenderSettings(show_shadow=settings.show_shadow))
        self.window = CompanionWindow(self)
        if options.size:
            self.window.set_character_size(options.size)
        self.tray: SystemTray | None = None
        self.settings_window: SettingsWindow | None = None
        self.shutdown = ShutdownSequence()

        self._listening = False
        self._quitting = False
        self._last_status: CaptureStatusInfo | None = None
        self._status_history: list[str] = []
        self._last_frame_time = time.perf_counter()
        self._last_output: DanceOutput | None = None
        self._idle_for = 0.0
        self._frame_ms: deque[float] = deque(maxlen=240)
        self._render_ms: deque[float] = deque(maxlen=240)
        self._frame_stamps: deque[float] = deque(maxlen=240)
        self._frames_total = 0
        self._started_wall = time.perf_counter()
        self._started_cpu = time.process_time()
        self._last_frame: FrameImage | None = None

        self._frame_timer = QTimer(self)
        self._frame_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._frame_timer.timeout.connect(self._on_frame)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(STATUS_POLL_MS)
        self._status_timer.timeout.connect(self._on_status)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(lambda: self.store.save(self.settings))
        qapp.aboutToQuit.connect(self._shutdown)

    # ------------------------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------------------------
    def start(self) -> None:
        try:
            self.renderer.initialize(*self.window.physical_size())
        except Exception as exc:
            log.exception("renderer initialisation failed")
            raise RendererUnavailable(f"The 3D renderer could not start: {exc}") from exc
        self.shutdown.add("renderer", self.renderer.dispose)
        self._apply_shadow()
        self.window.resized.connect(self.renderer.resize)
        self.window.moved.connect(self._on_moved)
        width, height = self.window.width(), self.window.height()
        self.window.move(wm.initial_position((width, height), (self.settings.window_x, self.settings.window_y)))
        wm.apply_window_flags(self.window, self.capabilities, self.settings.always_on_top, self.settings.click_through)
        self.window.show()
        self._sync_tray()

        self.worker.start()
        self.shutdown.add("analyzer", self.worker.stop)
        if self.capture is not None:
            self.shutdown.add("audio capture", self.capture.dispose)
            if self.settings.listen_on_start:
                self.start_listening()
        self._apply_frame_rate()
        self._frame_timer.start()
        self._status_timer.start()
        self._on_status()
        for notice in self.store.notices:
            self._notify(notice)
        if self.options.smoke_test > 0:
            QTimer.singleShot(int(self.options.smoke_test * 1000), self._finish_smoke_test)
        log.info("%s started (%s, Qt platform %s)", APP_NAME, self.renderer.description, self.qapp.platformName())

    def quit(self) -> None:
        self._shutdown()
        self.qapp.quit()

    def _shutdown(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        log.info("shutting down")
        self._frame_timer.stop()
        self._status_timer.stop()
        self._listening = False
        if self.tray is not None:
            self.tray.hide()
        self.store.save(self.settings)
        for name, ok in self.shutdown.run():
            log.info("shutdown %s: %s", name, "ok" if ok else "FAILED")
        if self.settings_window is not None:
            self.settings_window.close()
        self.window.close()

    # ------------------------------------------------------------------------------------
    # frame loop
    # ------------------------------------------------------------------------------------
    def _apply_frame_rate(self, idle: bool = False) -> None:
        fps = self.settings.effective_fps
        if self.options.fps:
            fps = min(30, self.options.fps) if self.settings.power_saving else self.options.fps
        if idle:
            fps = min(fps, IDLE_FPS)
        if not self.window.isVisible():
            fps = 5
        interval = max(1, int(round(1000.0 / fps)))
        if self._frame_timer.interval() != interval:
            self._frame_timer.setInterval(interval)

    def _inputs(self, dt: float) -> tuple[AudioFeatures, float, list]:
        if self.demo is not None:
            features, events = self.demo.update(dt)
            return features, 0.0, events
        features, wall = self.worker.latest()
        events = self.worker.drain_events()
        if not self._listening:
            return SILENT_FEATURES, 0.0, []
        age = time.monotonic() - wall if wall > 0 else 1e9
        return features, age, events

    def _on_frame(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_frame_time
        self._last_frame_time = now
        if not self.window.isVisible():
            return
        features, age, events = self._inputs(dt)
        output = self.dance.update(dt, features, age, events)
        self._last_output = output
        pose = self.animation.update(dt, output)
        start = time.perf_counter()
        frame = self.renderer.render(pose)
        rendered = time.perf_counter()
        self.window.set_frame(frame)
        self._last_frame = frame
        self._render_ms.append((rendered - start) * 1000.0)
        self._frame_ms.append((time.perf_counter() - now) * 1000.0)
        self._frame_stamps.append(now)
        self._frames_total += 1
        idle = output.state == DanceState.IDLE and output.weight < 0.02
        self._idle_for = self._idle_for + dt if idle else 0.0
        self._apply_frame_rate(idle=self._idle_for > IDLE_POWER_SAVE_AFTER and not self.settings.debug_mode)

    # ------------------------------------------------------------------------------------
    # capture status
    # ------------------------------------------------------------------------------------
    def _on_status(self) -> None:
        info = self.capture_status()
        if self.capture is not None:
            info = self.capture.poll(STATUS_POLL_MS / 1000.0)
        if self._last_status is None or (info.status, info.message, info.source_name) != (
            self._last_status.status,
            self._last_status.message,
            self._last_status.source_name,
        ):
            previous = self._last_status
            self._last_status = info
            self._status_history.append(info.status.name)
            self.window.set_status(info, self._listening)
            if self.tray is not None:
                self.tray.update_status(info)
            if self.settings_window is not None:
                self.settings_window.update_status(info)
            if info.status == CaptureStatus.PERMISSION_DENIED and (previous is None or previous.status != info.status):
                self._notify("EVE needs permission to hear system audio. " + info.message)
                self.show_settings()

    def capture_status(self) -> CaptureStatusInfo:
        if self.demo is not None:
            return CaptureStatusInfo(
                CaptureStatus.STOPPED, "Demo mode: dancing to a built-in virtual song (no audio capture)."
            )
        if self.capture is None:
            return CaptureStatusInfo(CaptureStatus.STOPPED, "Audio capture disabled (--no-audio).")
        return self.capture.status

    # ------------------------------------------------------------------------------------
    # AppController implementation (used by the UI)
    # ------------------------------------------------------------------------------------
    def start_listening(self) -> None:
        if self.capture is None:
            return
        self._listening = True
        self.capture.start(self.settings.audio_source_id)
        self._after_listening_change()

    def stop_listening(self) -> None:
        if self.capture is None:
            return
        self._listening = False
        self.capture.stop()
        self.buffer.reset()
        self._after_listening_change()

    def retry_capture(self) -> None:
        if self.capture is None:
            return
        self._listening = True
        self.capture.retry()
        self._after_listening_change()

    def _after_listening_change(self) -> None:
        self._last_status = None
        self._on_status()
        if self.tray is not None:
            self.tray.refresh()
        if self.settings_window is not None:
            self.settings_window.refresh()

    def can_listen(self) -> bool:
        return self.capture is not None

    def is_listening(self) -> bool:
        return self._listening

    def audio_sources(self, refresh: bool = False) -> list[AudioSource]:
        return self.capture.get_supported_sources(refresh) if self.capture is not None else []

    def set_audio_source(self, source_id: str | None) -> None:
        self.settings.audio_source_id = source_id
        self._save_timer.start()
        if self._listening and self.capture is not None:
            self.capture.stop()
            self.capture.start(source_id)
            self._after_listening_change()

    def audio_level(self) -> float:
        if self.capture is None or not self._listening:
            return self.latest_features().energy if self.demo is not None else 0.0
        peak = self.capture.peak
        if peak <= 1e-6:
            return 0.0
        return max(0.0, min(1.0, (20 * math.log10(peak) + 60.0) / 60.0))

    def update_setting(self, name: str, value: Any) -> None:
        data = self.settings.to_dict()
        data[name] = value
        validated, _ = validate(data)
        value = getattr(validated, name)
        if getattr(self.settings, name) == value:
            return
        setattr(self.settings, name, value)
        self._apply_setting(name)
        self._save_timer.start()

    def _apply_setting(self, name: str) -> None:
        s = self.settings
        if name == "sensitivity":
            self.worker.set_sensitivity(s.sensitivity)
        elif name == "dance_intensity":
            self.dance.settings.intensity = s.dance_intensity
        elif name == "reduced_motion":
            self.dance.settings.reduced_motion = s.reduced_motion
            self.animation.set_reduced_motion(s.reduced_motion)
        elif name == "character_size":
            self.window.set_character_size(s.character_size)
        elif name in ("always_on_top", "click_through"):
            if name == "click_through" and s.click_through and not (self.capabilities.system_tray and s.show_tray_icon):
                s.click_through = False
            wm.apply_window_flags(self.window, self.capabilities, s.always_on_top, s.click_through)
        elif name in ("power_saving", "target_fps"):
            self._apply_frame_rate()
        elif name == "show_tray_icon":
            if not s.show_tray_icon and s.click_through:
                s.click_through = False
                wm.apply_window_flags(self.window, self.capabilities, s.always_on_top, False)
            if not s.show_tray_icon and not self.window.isVisible():
                self.window.show()
            self._sync_tray()
        elif name == "show_shadow":
            self._apply_shadow()
        if self.tray is not None:
            self.tray.refresh()
        if self.settings_window is not None and name in ("click_through", "always_on_top", "show_tray_icon"):
            self.settings_window.sync_from_settings()

    def _apply_shadow(self) -> None:
        character = self.renderer.character
        if character is not None:
            character.shadow.show() if self.settings.show_shadow else character.shadow.hide()

    def _sync_tray(self) -> None:
        want = self.settings.show_tray_icon and self.capabilities.system_tray
        if want and self.tray is None:
            self.tray = SystemTray(self)
            self.tray.show()
            if self._last_status is not None:
                self.tray.update_status(self._last_status)
        elif not want and self.tray is not None:
            self.tray.hide()
            self.tray = None

    def reset_settings(self) -> None:
        position = (self.settings.window_x, self.settings.window_y)
        self.settings = self.store.reset()
        self.settings.window_x, self.settings.window_y = position
        for name in (
            "sensitivity",
            "dance_intensity",
            "reduced_motion",
            "character_size",
            "always_on_top",
            "power_saving",
            "show_tray_icon",
            "show_shadow",
        ):
            self._apply_setting(name)
        wm.apply_window_flags(self.window, self.capabilities, self.settings.always_on_top, self.settings.click_through)
        if self.settings_window is not None:
            self.settings_window.sync_from_settings()

    def set_companion_visible(self, visible: bool) -> None:
        if not visible and not (self.tray is not None):
            return  # without a tray there would be no way to bring EVE back
        self.window.setVisible(visible)
        self._apply_frame_rate()
        if self.tray is not None:
            self.tray.refresh()

    def companion_visible(self) -> bool:
        return self.window.isVisible()

    def show_settings(self) -> None:
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self, self.renderer.description)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def open_log_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.log_dir)))

    def open_privacy_settings(self) -> None:
        if sys.platform == "darwin":
            QDesktopServices.openUrl(QUrl(PRIVACY_SETTINGS_URL))

    def play_movement(self, name: str) -> None:
        self.dance.request_movement(name)

    def movement_names(self) -> list[str]:
        return sorted(self.dance.library)

    def poke(self) -> None:
        self.animation.poke()

    def latest_features(self) -> AudioFeatures:
        if self.demo is not None:
            return self.demo.update(0.0)[0]
        return self.worker.latest()[0] if self._listening else SILENT_FEATURES

    def debug_snapshot(self) -> dict[str, Any]:
        out = self._last_output
        fps = 0.0
        if len(self._frame_stamps) > 1:
            span = self._frame_stamps[-1] - self._frame_stamps[0]
            fps = (len(self._frame_stamps) - 1) / span if span > 0 else 0.0
        status = self.capture_status()
        return {
            "state": out.state.value if out else "",
            "movement": out.movement if out else "",
            "drive": out.drive if out else 0.0,
            "weight": out.weight if out else 0.0,
            "beat_locked": out.beat_locked if out else False,
            "dance_bpm": self.dance.tempo_bpm,
            "fps": fps,
            "frame_ms": sum(self._frame_ms) / len(self._frame_ms) if self._frame_ms else 0.0,
            "render_size": f"{self.renderer.width}×{self.renderer.height}px",
            "analysis_ms": self.worker.avg_process_ms,
            "source": status.source_name or status.backend,
            "overruns": self.buffer.overruns,
            "samples": self.capture.samples_received if self.capture else 0,
        }

    def _on_moved(self, x: int, y: int) -> None:
        self.settings.window_x, self.settings.window_y = x, y
        self._save_timer.start()

    def _notify(self, text: str) -> None:
        log.info("notice: %s", text)
        if self.tray is not None:
            self.tray.icon.showMessage(APP_NAME, text, QSystemTrayIcon.MessageIcon.Information, 8000)

    # ------------------------------------------------------------------------------------
    # smoke test / measurements
    # ------------------------------------------------------------------------------------
    def performance_report(self) -> dict[str, Any]:
        wall = time.perf_counter() - self._started_wall
        cpu = time.process_time() - self._started_cpu
        frame_ms = sorted(self._frame_ms)
        render_ms = sorted(self._render_ms)

        def pct(values: list[float], q: float) -> float:
            return round(values[min(len(values) - 1, int(q * len(values)))], 2) if values else 0.0

        try:
            import resource  # POSIX only

            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
        except ImportError:
            rss_mb = 0.0
        snap = self.debug_snapshot()
        return {
            "seconds": round(wall, 1),
            "frames": self._frames_total,
            "avg_fps": round(self._frames_total / wall, 1) if wall > 0 else 0,
            "frame_ms_p50": pct(frame_ms, 0.5),
            "frame_ms_p95": pct(frame_ms, 0.95),
            "render_ms_p50": pct(render_ms, 0.5),
            "render_ms_p95": pct(render_ms, 0.95),
            "process_cpu_percent": round(100 * cpu / wall, 1) if wall > 0 else 0,
            "max_rss_mb": round(rss_mb, 1),
            "render_size": snap["render_size"],
            "renderer": self.renderer.description,
            "qt_platform": self.qapp.platformName(),
            "capture_status_history": self._status_history,
            "samples_received": snap["samples"],
            "buffer_overruns": snap["overruns"],
            "analysis_ms_per_hop": round(self.worker.avg_process_ms, 3),
            "dance_state": snap["state"],
            "movement": snap["movement"],
        }

    def _finish_smoke_test(self) -> None:
        import json

        report = self.performance_report()
        if self.options.screenshot and self._last_frame is not None:
            from PySide6.QtGui import QImage

            f = self._last_frame
            image = QImage(f.pixels.data, f.width, f.height, f.stride, QImage.Format.Format_ARGB32_Premultiplied)
            report["screenshot_saved"] = bool(image.save(self.options.screenshot))
        print(json.dumps(report, indent=2), flush=True)
        self.quit()
