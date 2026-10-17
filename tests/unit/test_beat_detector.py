"""Onsets vs beats, cooldowns, tempo accuracy and (honest) confidence."""

from __future__ import annotations

import numpy as np
import pytest

from eve.audio.analyzer import AudioAnalyzer
from eve.audio.audio_features import PulseKind
from eve.audio.beat_detector import BeatTracker, OnsetDetector
from eve.audio.tempo_estimator import TempoEstimate, TempoEstimator
from tests.fixtures import synthetic_audio as sa


def _run(signal: np.ndarray) -> tuple[list, list]:
    analyzer = AudioAnalyzer(48000)
    return analyzer.process_block(signal)


def test_onset_detector_respects_min_interval() -> None:
    det = OnsetDetector(fps=100, min_interval=0.2)
    onsets = []
    for i in range(400):
        value = 1.0 if i % 5 == 0 else 0.0  # a spike every 50 ms
        if det.update(value, i / 100, 0.01) is not None:
            onsets.append(i / 100)
    gaps = np.diff(onsets)
    assert len(onsets) > 5
    assert gaps.min() >= 0.2 - 1e-9


def test_onset_detector_ignores_constant_signal() -> None:
    det = OnsetDetector(fps=100)
    hits = [det.update(0.5, i / 100, 0.01) for i in range(300)]
    assert all(h is None for h in hits)


@pytest.mark.parametrize("bpm", [90, 105, 120, 128, 140])
def test_tempo_is_estimated_for_clear_beats(bpm: float) -> None:
    frames, _ = _run(np.concatenate([sa.silence(0.5), sa.beat_track(12.0, bpm=bpm, with_hats=False)]))
    final = frames[-1]
    assert final.tempo_confidence > 0.5
    assert final.tempo_bpm == pytest.approx(bpm, rel=0.03)


def test_beats_are_phase_aligned_with_kicks() -> None:
    bpm = 120.0
    period = 60.0 / bpm
    _, events = _run(np.concatenate([sa.silence(1.0), sa.beat_track(14.0, bpm=bpm)]))
    beats = np.array([e.time for e in events if e.kind == PulseKind.BEAT and e.time > 8.0])
    assert len(beats) >= 10
    error = np.abs(((beats - 1.0 + period / 2) % period) - period / 2)
    assert error.mean() < 0.04  # within 40 ms of the true kick on average


def test_noise_gives_low_tempo_confidence_and_no_beats() -> None:
    frames, events = _run(sa.noise(12.0, amp=0.2))
    assert frames[-1].tempo_confidence < 0.3
    assert frames[-1].tempo_bpm == 0.0
    assert not [e for e in events if e.kind == PulseKind.BEAT]


def test_steady_tone_is_not_beat_like() -> None:
    frames, events = _run(sa.tone(10.0, amp=0.4))
    assert frames[-1].tempo_bpm == 0.0
    assert not [e for e in events if e.kind == PulseKind.BEAT]


def test_beats_stop_quickly_after_music_stops() -> None:
    _, events = _run(np.concatenate([sa.beat_track(12.0, bpm=120), sa.silence(5.0)]))
    late = [e for e in events if e.kind == PulseKind.BEAT and e.time > 12.0 + 1.5]
    assert late == []


def test_surge_event_on_sudden_energy_increase() -> None:
    _, events = _run(sa.energy_step(8.0, 6.0))
    surges = [e for e in events if e.kind == PulseKind.SURGE]
    assert surges, "a quiet→loud step should produce a surge"
    assert 7.5 < surges[0].time < 10.0


def test_beat_tracker_does_nothing_without_confidence() -> None:
    tracker = BeatTracker(min_confidence=0.3)
    weak = TempoEstimate(120.0, 0.1, 0.5)
    for i in range(200):
        assert tracker.update(i * 0.01, weak, 0.9, beat_offset=0.0, dt=0.01) is None
    assert not tracker.locked


def test_tempo_estimator_needs_history_before_reporting() -> None:
    est = TempoEstimator(fps=100, min_history_seconds=3.0)
    for i in range(250):
        est.push(1.0 if i % 50 == 0 else 0.0, 0.01)
    assert est.current.confidence == 0.0
