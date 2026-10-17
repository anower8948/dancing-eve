"""Shared recorder-thread implementation on top of the SoundCard library.

Used for WASAPI loopback (Windows), PulseAudio/PipeWire monitor sources (Linux) and
virtual loopback devices such as BlackHole (macOS fallback). Subclasses only decide which
devices are valid *output* capture sources — never microphones.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from eve.audio.capture_interface import AudioCaptureBackend, AudioSource, SourceKind
from eve.audio.capture_status import CaptureStatus

log = logging.getLogger(__name__)

SAMPLE_RATE = 48000
BLOCK_FRAMES = 1024
DEFAULT_CHECK_INTERVAL = 2.0


def com_initialize() -> None:
    """WASAPI is COM-based: every thread that touches it needs COM initialised (MTA)."""
    if sys.platform.startswith("win"):
        import ctypes

        ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
        ole32.CoInitializeEx(None, 0x0)  # COINIT_MULTITHREADED; S_FALSE/RPC_E_CHANGED_MODE are fine


def com_uninitialize() -> None:
    if sys.platform.startswith("win"):
        import ctypes

        ctypes.windll.ole32.CoUninitialize()  # type: ignore[attr-defined]


def run_in_com_thread(func: Callable[[], Any], timeout: float = 10.0) -> Any:
    """Run ``func`` on a short-lived thread with COM initialised (Windows), else inline."""
    if not sys.platform.startswith("win"):
        return func()
    result: dict[str, Any] = {}

    def target() -> None:
        com_initialize()
        try:
            result["value"] = func()
        except BaseException as exc:
            result["error"] = exc
        finally:
            com_uninitialize()

    thread = threading.Thread(target=target, name="eve-com-enum", daemon=True)
    thread.start()
    thread.join(timeout)
    if "error" in result:
        raise result["error"]
    return result.get("value")


class SoundCardBackend(AudioCaptureBackend):
    key = "soundcard"
    source_kind = SourceKind.SYSTEM_OUTPUT
    follows_default = True  # reopen when the default output device changes

    def __init__(self, on_samples, on_status) -> None:
        super().__init__(on_samples, on_status)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- subclass hooks --------------------------------------------------------------------
    def _devices(self, sc: Any) -> list[tuple[AudioSource, Any]]:
        """Return (AudioSource, soundcard microphone object) for valid capture sources."""
        raise NotImplementedError

    def _default_marker(self, sc: Any) -> str:
        """A string that changes when the default output device changes."""
        try:
            return str(sc.default_speaker().name)
        except Exception:
            return ""

    # -- interface -------------------------------------------------------------------------
    @classmethod
    def availability(cls) -> tuple[bool, str]:
        try:
            run_in_com_thread(lambda: __import__("soundcard"))
        except Exception as exc:  # missing libpulse, broken install, ...
            return False, f"SoundCard library unavailable: {exc}"
        return True, ""

    def get_supported_sources(self) -> list[AudioSource]:
        def enumerate_sources() -> list[AudioSource]:
            import soundcard as sc

            return [source for source, _ in self._devices(sc)]

        try:
            return list(run_in_com_thread(enumerate_sources) or [])
        except Exception:
            log.exception("[%s] could not enumerate devices", self.key)
            return []

    def start_capture(self, source_id: str | None = None) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._set_status(CaptureStatus.CONNECTING, "Opening audio device…")
        self._thread = threading.Thread(
            target=self._run, args=(source_id,), name=f"eve-capture-{self.key}", daemon=True
        )
        self._thread.start()

    def stop_capture(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(3.0)
            if thread.is_alive():
                log.warning("[%s] capture thread did not stop in time", self.key)
        self._thread = None
        self._set_status(CaptureStatus.STOPPED)

    # -- recorder thread ------------------------------------------------------------------
    def _resolve(self, sc: Any, source_id: str | None) -> tuple[AudioSource, Any] | None:
        devices = self._devices(sc)
        if not devices:
            return None
        if source_id:
            for source, mic in devices:
                if source.id == source_id:
                    return source, mic
            return None
        for source, mic in devices:
            if source.is_default:
                return source, mic
        return devices[0]

    def _run(self, source_id: str | None) -> None:
        com_initialize()
        try:
            import soundcard as sc

            while not self._stop.is_set():
                resolved = self._resolve(sc, source_id)
                if resolved is None:
                    wanted = source_id or "a default output"
                    self._set_status(CaptureStatus.DEVICE_UNAVAILABLE, f"No capturable output device found ({wanted}).")
                    return
                source, mic = resolved
                marker = self._default_marker(sc)
                reopen = self._record(sc, source, mic, marker, follow=source_id is None and self.follows_default)
                if not reopen:
                    return
                log.info("[%s] default output changed; reopening", self.key)
        except Exception as exc:
            log.exception("[%s] capture failed", self.key)
            if not self._stop.is_set():
                self._set_status(CaptureStatus.DEVICE_UNAVAILABLE, f"Audio device error: {exc}")
        finally:
            com_uninitialize()

    def _record(self, sc: Any, source: AudioSource, mic: Any, marker: str, follow: bool) -> bool:
        """Record until stopped. Returns True when the stream should be reopened."""
        self._set_status(CaptureStatus.CONNECTING, f"Opening {source.name}…", source.name)
        with mic.recorder(samplerate=SAMPLE_RATE, blocksize=BLOCK_FRAMES) as recorder:
            self._set_status(CaptureStatus.RECEIVING_AUDIO, "", source.name)
            last_check = time.monotonic()
            while not self._stop.is_set():
                data = recorder.record(numframes=BLOCK_FRAMES)
                if data is not None and data.size:
                    self._emit_samples(data, SAMPLE_RATE)
                now = time.monotonic()
                if follow and now - last_check > DEFAULT_CHECK_INTERVAL:
                    last_check = now
                    if self._default_marker(sc) != marker:
                        return True
        return False
