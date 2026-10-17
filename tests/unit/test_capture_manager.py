"""Capture manager status honesty, retries and cleanup (with fake backends — no real I/O)."""

from __future__ import annotations

import numpy as np

from eve.audio.capture_interface import AudioCaptureBackend, AudioSource, SourceKind
from eve.audio.capture_manager import NO_SAMPLES_TIMEOUT, SILENCE_TIMEOUT, CaptureManager
from eve.audio.capture_status import CaptureStatus
from eve.audio.sample_buffer import SampleBuffer


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


class FakeBackend(AudioCaptureBackend):
    key = "fake"
    display_name = "Fake"
    instances: list[FakeBackend] = []
    available = True
    fail_with: CaptureStatus | None = None

    def __init__(self, on_samples, on_status) -> None:
        super().__init__(on_samples, on_status)
        self.started = 0
        self.stopped = 0
        FakeBackend.instances.append(self)

    @classmethod
    def availability(cls):
        return (cls.available, "" if cls.available else "not on this OS")

    def start_capture(self, source_id=None) -> None:
        self.started += 1
        if FakeBackend.fail_with is not None:
            self._set_status(FakeBackend.fail_with, "boom")
        else:
            self._set_status(CaptureStatus.RECEIVING_AUDIO, "", "Fake output")

    def stop_capture(self) -> None:
        self.stopped += 1
        self._set_status(CaptureStatus.STOPPED)

    def get_supported_sources(self):
        return [AudioSource("fake:out", "Fake output", SourceKind.SYSTEM_OUTPUT, True)]

    def push(self, samples: np.ndarray, rate: int = 48000) -> None:
        self._emit_samples(samples, rate)


def make(clock: Clock) -> tuple[CaptureManager, FakeBackend, SampleBuffer]:
    FakeBackend.instances.clear()
    FakeBackend.available = True
    FakeBackend.fail_with = None
    buffer = SampleBuffer()
    manager = CaptureManager(buffer, [FakeBackend], clock=clock)
    return manager, FakeBackend.instances[-1], buffer


def test_open_stream_without_samples_reports_no_audio() -> None:
    clock = Clock()
    manager, backend, _ = make(clock)
    manager.start()
    clock.t += NO_SAMPLES_TIMEOUT + 0.5
    info = manager.poll()
    assert info.status == CaptureStatus.NO_AUDIO_DETECTED
    assert "no audio data" in info.message


def test_digital_silence_reports_nothing_playing() -> None:
    clock = Clock()
    manager, backend, _ = make(clock)
    manager.start()
    for _ in range(10):
        clock.t += 0.5
        backend.push(np.zeros((480, 2), dtype=np.float32))
    clock.t += 0.1
    assert SILENCE_TIMEOUT < 5.5
    info = manager.poll()
    assert info.status == CaptureStatus.NO_AUDIO_DETECTED
    assert "nothing is playing" in info.message


def test_real_signal_reports_receiving_and_feeds_buffer() -> None:
    clock = Clock()
    manager, backend, buffer = make(clock)
    manager.start()
    backend.push(0.3 * np.ones((960, 2), dtype=np.float32))
    assert manager.peak > 0.29
    assert manager.poll().status == CaptureStatus.RECEIVING_AUDIO
    assert buffer.available() == 960  # downmixed to mono
    assert manager.samples_received == 960


def test_recoverable_failure_retries_with_backoff() -> None:
    clock = Clock()
    manager, backend, _ = make(clock)
    FakeBackend.fail_with = CaptureStatus.DEVICE_UNAVAILABLE
    manager.start()
    assert manager.poll().status == CaptureStatus.DEVICE_UNAVAILABLE
    starts = backend.started
    clock.t += 1.0
    manager.poll()
    assert backend.started == starts  # not yet
    FakeBackend.fail_with = None
    clock.t += 2.0
    manager.poll()
    assert backend.started == starts + 1
    assert manager.poll().status == CaptureStatus.CONNECTING  # stale failure is cleared
    backend.push(0.2 * np.ones(480, dtype=np.float32))
    assert manager.poll().status == CaptureStatus.RECEIVING_AUDIO


def test_permission_denied_is_not_retried_automatically() -> None:
    clock = Clock()
    manager, backend, _ = make(clock)
    FakeBackend.fail_with = CaptureStatus.PERMISSION_DENIED
    manager.start()
    for _ in range(20):
        clock.t += 5.0
        assert manager.poll().status == CaptureStatus.PERMISSION_DENIED
    assert backend.started == 1
    FakeBackend.fail_with = None
    manager.retry()  # the user's Retry button
    assert backend.started == 2


def test_no_backend_is_unsupported_not_microphone() -> None:
    FakeBackend.available = False
    manager = CaptureManager(SampleBuffer(), [FakeBackend], clock=Clock())
    manager.start()
    info = manager.poll()
    assert info.status == CaptureStatus.UNSUPPORTED
    assert "not on this OS" in info.message
    FakeBackend.available = True


def test_stop_and_dispose_release_the_backend() -> None:
    clock = Clock()
    manager, backend, _ = make(clock)
    manager.start()
    manager.stop()
    assert backend.stopped >= 1
    assert manager.poll().status == CaptureStatus.STOPPED
    manager.dispose()
    assert manager.has_backend is False


def test_callback_errors_never_escape_backend_threads() -> None:
    def bad_samples(*_a):
        raise RuntimeError("consumer bug")

    backend = FakeBackend(bad_samples, lambda _i: None)
    backend.push(np.zeros(10, dtype=np.float32))  # must not raise
