"""Capture status values shared by every capture backend and the UI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CaptureStatus(Enum):
    STOPPED = "stopped"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    CONNECTING = "connecting"
    RECEIVING_AUDIO = "receiving_audio"
    NO_AUDIO_DETECTED = "no_audio_detected"
    PERMISSION_DENIED = "permission_denied"
    DEVICE_UNAVAILABLE = "device_unavailable"
    UNSUPPORTED = "unsupported"
    ERROR = "error"

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def is_active(self) -> bool:
        """True while a capture stream is open (the privacy indicator is shown)."""
        return self in (CaptureStatus.CONNECTING, CaptureStatus.RECEIVING_AUDIO, CaptureStatus.NO_AUDIO_DETECTED)

    @property
    def is_failure(self) -> bool:
        return self in (
            CaptureStatus.PERMISSION_DENIED,
            CaptureStatus.DEVICE_UNAVAILABLE,
            CaptureStatus.UNSUPPORTED,
            CaptureStatus.ERROR,
        )

    @property
    def auto_retry(self) -> bool:
        """Failures that may fix themselves (device came back, transient error)."""
        return self in (CaptureStatus.DEVICE_UNAVAILABLE, CaptureStatus.ERROR)


_LABELS = {
    CaptureStatus.STOPPED: "Not listening",
    CaptureStatus.WAITING_FOR_PERMISSION: "Waiting for permission…",
    CaptureStatus.CONNECTING: "Connecting…",
    CaptureStatus.RECEIVING_AUDIO: "Listening",
    CaptureStatus.NO_AUDIO_DETECTED: "Listening — no audio detected",
    CaptureStatus.PERMISSION_DENIED: "Permission denied",
    CaptureStatus.DEVICE_UNAVAILABLE: "Audio device unavailable",
    CaptureStatus.UNSUPPORTED: "System audio capture unsupported",
    CaptureStatus.ERROR: "Capture error",
}


@dataclass(frozen=True)
class CaptureStatusInfo:
    status: CaptureStatus
    message: str = ""
    source_name: str = ""
    backend: str = ""
    timestamp: float = field(default_factory=time.monotonic)

    @property
    def text(self) -> str:
        return self.message or self.status.label
