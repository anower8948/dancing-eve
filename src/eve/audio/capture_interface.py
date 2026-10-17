"""Platform-independent system-audio capture interface.

A backend delivers raw output-audio samples through ``on_samples`` from its own thread
(or OS callback queue) and reports state through ``on_status``. Backends never analyse
audio and never touch the UI or renderer.

Rule: a backend must never fall back to a microphone. Only system-output capture (native
loopback / ScreenCaptureKit / monitor sources) or an explicitly virtual loopback device
are valid sources.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np

from eve.audio.capture_status import CaptureStatus, CaptureStatusInfo

# (samples, sample_rate). samples: float32, shape (frames,) or (frames, channels), range ±1.
SamplesCallback = Callable[[np.ndarray, int], None]
StatusCallback = Callable[[CaptureStatusInfo], None]

log = logging.getLogger(__name__)


class SourceKind(Enum):
    SYSTEM_OUTPUT = "system_output"  # everything the computer plays (SCK, WASAPI loopback)
    MONITOR = "monitor"  # PulseAudio/PipeWire monitor of one output sink
    VIRTUAL_DEVICE = "virtual_device"  # loopback driver such as BlackHole


@dataclass(frozen=True)
class AudioSource:
    id: str  # "<backend>:<device id>", unique across backends
    name: str
    kind: SourceKind
    is_default: bool = False
    description: str = ""


class AudioCaptureBackend(ABC):
    """Base class: status bookkeeping + callback plumbing. Subclasses implement I/O."""

    key: str = "base"  # short id used as the AudioSource.id prefix
    display_name: str = "Audio capture"

    def __init__(self, on_samples: SamplesCallback, on_status: StatusCallback) -> None:
        self._on_samples = on_samples
        self._on_status = on_status
        self._status_lock = threading.Lock()
        self._status = CaptureStatusInfo(CaptureStatus.STOPPED, backend=self.key)

    # -- availability --------------------------------------------------------------------
    @classmethod
    def availability(cls) -> tuple[bool, str]:
        """(available, reason). Must be cheap and must not prompt for permissions."""
        return True, ""

    # -- required operations ---------------------------------------------------------------
    @abstractmethod
    def start_capture(self, source_id: str | None = None) -> None:
        """Begin capturing asynchronously; progress is reported through ``on_status``."""

    @abstractmethod
    def stop_capture(self) -> None:
        """Stop capturing and release the OS device. Must be idempotent."""

    @abstractmethod
    def get_supported_sources(self) -> list[AudioSource]:
        """Enumerate capturable output sources (may be empty)."""

    def get_status(self) -> CaptureStatusInfo:
        with self._status_lock:
            return self._status

    def dispose(self) -> None:
        self.stop_capture()

    # -- helpers for subclasses ------------------------------------------------------------
    def _set_status(self, status: CaptureStatus, message: str = "", source_name: str = "") -> None:
        info = CaptureStatusInfo(status, message, source_name or self._status.source_name, self.key)
        with self._status_lock:
            changed = (info.status, info.message) != (self._status.status, self._status.message)
            self._status = info
        if changed:
            log.info("[%s] %s %s", self.key, status.name, message)
        try:
            self._on_status(info)
        except Exception:  # never let a UI callback kill a capture thread
            log.exception("status callback failed")

    def _emit_samples(self, samples: np.ndarray, sample_rate: int) -> None:
        try:
            self._on_samples(samples, sample_rate)
        except Exception:
            log.exception("samples callback failed")
