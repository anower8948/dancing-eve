"""Capture-manager → SampleBuffer → AnalyzerWorker thread, with synthetic audio.

This exercises the threaded pipeline end to end. It does NOT test real OS audio capture;
see docs/testing.md for the manual / ``--test-capture`` procedure.
"""

from __future__ import annotations

import threading
import time

import numpy as np

from eve.audio.analyzer import AnalyzerWorker
from eve.audio.audio_features import PulseKind
from eve.audio.capture_manager import CaptureManager
from eve.audio.capture_status import CaptureStatus
from eve.audio.sample_buffer import SampleBuffer
from tests.fixtures import synthetic_audio as sa
from tests.unit.test_capture_manager import FakeBackend


def test_threaded_pipeline_produces_beats_and_stops_cleanly() -> None:
    FakeBackend.instances.clear()
    FakeBackend.available = True
    FakeBackend.fail_with = None
    buffer = SampleBuffer()
    manager = CaptureManager(buffer, [FakeBackend])
    worker = AnalyzerWorker(buffer)
    worker.start()
    manager.start()
    backend = FakeBackend.instances[-1]
    signal = sa.beat_track(10.0, bpm=120)
    stereo = np.stack([signal, signal], axis=1)

    def feed() -> None:  # faster than real time, in 20 ms blocks, like an OS callback
        for start in range(0, stereo.shape[0], 960):
            backend.push(stereo[start : start + 960])
            time.sleep(0.0005)

    feeder = threading.Thread(target=feed)
    feeder.start()
    events = []
    deadline = time.monotonic() + 20.0
    while feeder.is_alive() or buffer.available() >= 512:
        events.extend(worker.drain_events())
        time.sleep(0.01)
        assert time.monotonic() < deadline
    feeder.join()
    time.sleep(0.2)
    events.extend(worker.drain_events())
    features, published = worker.latest()

    assert manager.poll().status == CaptureStatus.RECEIVING_AUDIO
    assert worker.hops_processed > 800
    assert any(e.kind == PulseKind.BEAT for e in events)
    assert features.music_activity > 0.9 and published > 0

    manager.dispose()
    worker.stop()
    assert not worker.running
    threads = [t.name for t in threading.enumerate()]
    assert "eve-analyzer" not in threads


def test_worker_survives_sample_rate_change() -> None:
    buffer = SampleBuffer(sample_rate=48000)
    worker = AnalyzerWorker(buffer)
    worker.start()
    buffer.write(sa.beat_track(1.0, sr=48000), 48000)
    time.sleep(0.3)
    buffer.write(sa.beat_track(1.0, sr=44100), 44100)
    time.sleep(0.3)
    features, _ = worker.latest()
    worker.stop()
    assert features.sample_rate == 44100
