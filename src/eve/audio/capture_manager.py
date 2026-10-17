"""Chooses a capture backend, feeds samples to the buffer, and reports honest status.

The backend only knows whether its stream is open. The manager additionally watches the
samples themselves, so the UI can distinguish "receiving real audio" from "stream open but
nothing arrives" and "connected but the system is silent". It also retries recoverable
failures with backoff. ``poll()`` must be called periodically (the app does it ~4×/s from
the main thread); there is no extra thread.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence

import numpy as np

from eve.audio.capture_interface import AudioCaptureBackend, AudioSource
from eve.audio.capture_status import CaptureStatus, CaptureStatusInfo
from eve.audio.sample_buffer import SampleBuffer, to_float32, to_mono

log = logging.getLogger(__name__)

NO_SAMPLES_TIMEOUT = 3.0  # stream open but no sample data for this long -> NO_AUDIO_DETECTED
SILENCE_TIMEOUT = 4.0  # samples arrive but are digital silence for this long
SIGNAL_PEAK_THRESHOLD = 10 ** (-70 / 20)  # anything above -70 dBFS counts as real signal
RETRY_BACKOFF = (2.0, 5.0, 10.0, 20.0, 30.0)

BackendFactory = Callable[..., AudioCaptureBackend]


class CaptureManager:
    def __init__(
        self,
        buffer: SampleBuffer,
        backend_classes: Sequence[type[AudioCaptureBackend]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.buffer = buffer
        self._clock = clock
        if backend_classes is None:
            from eve.audio.platforms import default_backend_classes

            backend_classes = default_backend_classes()
        self._classes = list(backend_classes)
        self._backends: dict[str, AudioCaptureBackend] = {}
        self._unavailable: dict[str, str] = {}
        self._lock = threading.Lock()
        self._active: AudioCaptureBackend | None = None
        self._source_id: str | None = None
        self.wanted = False
        self._backend_status = CaptureStatusInfo(CaptureStatus.STOPPED)
        self._status = CaptureStatusInfo(CaptureStatus.STOPPED)
        self._started_at = 0.0
        self._last_samples_at = 0.0
        self._last_signal_at = 0.0
        self._retry_at: float | None = None
        self._retries = 0
        self.samples_received = 0
        self.peak = 0.0  # recent peak level (decays in poll), for the UI meter
        self._sources_cache: list[AudioSource] | None = None
        self._probe_backends()

    # -- backends --------------------------------------------------------------------------
    def _probe_backends(self) -> None:
        for cls in self._classes:
            ok, reason = cls.availability()
            if ok:
                self._backends[cls.key] = cls(self._on_samples, self._on_backend_status)
            else:
                self._unavailable[cls.key] = reason
                log.info("capture backend %s unavailable: %s", cls.key, reason)

    @property
    def unavailable_reasons(self) -> dict[str, str]:
        return dict(self._unavailable)

    @property
    def has_backend(self) -> bool:
        return bool(self._backends)

    def get_supported_sources(self, refresh: bool = False) -> list[AudioSource]:
        if self._sources_cache is None or refresh:
            sources: list[AudioSource] = []
            for backend in self._backends.values():
                sources.extend(backend.get_supported_sources())
            self._sources_cache = sources
        return list(self._sources_cache)

    def _backend_for(self, source_id: str | None) -> AudioCaptureBackend | None:
        if source_id:
            key = source_id.split(":", 1)[0]
            backend = self._backends.get(key)
            if backend is not None:
                return backend
        # Default: the first available backend that has a default source.
        for backend in self._backends.values():
            sources = backend.get_supported_sources()
            if any(s.is_default for s in sources):
                return backend
        for backend in self._backends.values():
            if backend.get_supported_sources():
                return backend
        return None

    # -- control ---------------------------------------------------------------------------
    @property
    def source_id(self) -> str | None:
        return self._source_id

    def start(self, source_id: str | None = None) -> None:
        self.wanted = True
        self._source_id = source_id
        self._retries = 0
        self._start_backend()

    def _start_backend(self) -> None:
        self._retry_at = None
        if not self._backends:
            reasons = "; ".join(self._unavailable.values()) or "no capture backend for this OS"
            self._set_status(
                CaptureStatusInfo(CaptureStatus.UNSUPPORTED, f"System audio capture is not available: {reasons}")
            )
            return
        backend = self._backend_for(self._source_id)
        if backend is None:
            if self._source_id:
                message = f"The selected source ({self._source_id}) is not available."
            else:
                message = "No system-audio source was found."
            self._set_status(CaptureStatusInfo(CaptureStatus.DEVICE_UNAVAILABLE, message))
            self._schedule_retry()
            return
        if self._active is not None and self._active is not backend:
            self._active.stop_capture()
        self._active = backend
        now = self._clock()
        self._started_at = now
        self._last_samples_at = 0.0
        self._last_signal_at = 0.0
        source = self._source_id if self._source_id and self._source_id.startswith(backend.key + ":") else None
        log.info("starting capture with backend %s (source %s)", backend.key, source or "default")
        backend.start_capture(source)
        self.poll()

    def stop(self) -> None:
        self.wanted = False
        self._retry_at = None
        if self._active is not None:
            self._active.stop_capture()
        self._active = None
        self.peak = 0.0
        self._set_status(CaptureStatusInfo(CaptureStatus.STOPPED))

    def retry(self) -> None:
        """Manual retry (UI button): restart from scratch, re-enumerating sources."""
        if self._active is not None:
            self._active.stop_capture()
            self._active = None
        self._sources_cache = None
        self.start(self._source_id)

    def dispose(self) -> None:
        self.stop()
        for backend in self._backends.values():
            try:
                backend.dispose()
            except Exception:
                log.exception("error disposing backend %s", backend.key)
        self._backends.clear()

    # -- callbacks (capture threads) -----------------------------------------------------
    def _on_samples(self, samples: np.ndarray, sample_rate: int) -> None:
        mono = to_mono(to_float32(samples))
        if mono.size == 0:
            return
        now = self._clock()
        peak = float(np.max(np.abs(mono)))
        with self._lock:
            self._last_samples_at = now
            if peak > SIGNAL_PEAK_THRESHOLD:
                self._last_signal_at = now
            self.samples_received += mono.shape[0]
            if peak > self.peak:
                self.peak = peak
        self.buffer.write(mono, sample_rate)

    def _on_backend_status(self, info: CaptureStatusInfo) -> None:
        with self._lock:
            self._backend_status = info

    # -- status ------------------------------------------------------------------------------
    @property
    def status(self) -> CaptureStatusInfo:
        with self._lock:
            return self._status

    def _set_status(self, info: CaptureStatusInfo) -> None:
        with self._lock:
            changed = (info.status, info.message) != (self._status.status, self._status.message)
            self._status = info
        if changed:
            log.info("capture status: %s %s", info.status.name, info.message)

    def _schedule_retry(self) -> None:
        if not self.wanted:
            return
        delay = RETRY_BACKOFF[min(self._retries, len(RETRY_BACKOFF) - 1)]
        self._retries += 1
        self._retry_at = self._clock() + delay
        log.info("retrying capture in %.0fs", delay)

    def poll(self, dt: float = 0.25) -> CaptureStatusInfo:
        now = self._clock()
        with self._lock:
            backend_info = self._backend_status
            last_samples = self._last_samples_at
            last_signal = self._last_signal_at
            self.peak *= 0.5 ** (dt / 0.3)  # meter decay
        if not self.wanted:
            return self.status
        if self._retry_at is not None:
            if now >= self._retry_at:
                self._start_backend()
            return self.status
        if self._active is None:
            return self.status

        state = backend_info.status
        source = backend_info.source_name
        if state.is_failure:
            self._set_status(backend_info)
            if state.auto_retry:
                self._active.stop_capture()
                self._schedule_retry()
            return self.status
        if state in (CaptureStatus.STOPPED, CaptureStatus.CONNECTING, CaptureStatus.WAITING_FOR_PERMISSION):
            if state == CaptureStatus.STOPPED:
                state = CaptureStatus.CONNECTING
            if now - self._started_at > 20.0 and state == CaptureStatus.CONNECTING:
                self._set_status(
                    CaptureStatusInfo(
                        CaptureStatus.ERROR, "Timed out while opening the audio stream.", source, backend_info.backend
                    )
                )
                self._active.stop_capture()
                self._schedule_retry()
                return self.status
            self._set_status(CaptureStatusInfo(state, backend_info.message, source, backend_info.backend))
            return self.status

        # Backend says the stream is open: verify with the actual samples.
        current = self.status.status
        waiting = current not in (CaptureStatus.RECEIVING_AUDIO, CaptureStatus.NO_AUDIO_DETECTED)
        if last_samples == 0.0 or now - last_samples > NO_SAMPLES_TIMEOUT:
            if now - max(self._started_at, last_samples) > NO_SAMPLES_TIMEOUT:
                self._set_status(
                    CaptureStatusInfo(
                        CaptureStatus.NO_AUDIO_DETECTED,
                        f"Connected to {source or 'the source'}, but no audio data is arriving.",
                        source,
                        backend_info.backend,
                    )
                )
            elif waiting:
                self._set_status(
                    CaptureStatusInfo(CaptureStatus.CONNECTING, "Waiting for audio data…", source, backend_info.backend)
                )
            return self.status
        if last_signal == 0.0 or now - last_signal > SILENCE_TIMEOUT:
            if now - max(self._started_at, last_signal) > SILENCE_TIMEOUT:
                self._set_status(
                    CaptureStatusInfo(
                        CaptureStatus.NO_AUDIO_DETECTED,
                        "Listening — nothing is playing right now.",
                        source,
                        backend_info.backend,
                    )
                )
            elif waiting:
                self._set_status(
                    CaptureStatusInfo(
                        CaptureStatus.CONNECTING, "Connected — checking for sound…", source, backend_info.backend
                    )
                )
            return self.status
        self._retries = 0
        self._set_status(CaptureStatusInfo(CaptureStatus.RECEIVING_AUDIO, "", source, backend_info.backend))
        return self.status
