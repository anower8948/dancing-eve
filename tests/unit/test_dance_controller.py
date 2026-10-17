"""Dance state machine, choreography variety, fallbacks and settling to idle."""

from __future__ import annotations

import random
from collections import Counter

import numpy as np
import pytest

from eve.animation.animation_controller import AnimationController
from eve.audio.audio_features import SILENT_FEATURES, AudioFeatures, PulseEvent, PulseKind
from eve.character.character_rig import Ch
from eve.dance.choreography import Choreographer
from eve.dance.dance_controller import DanceController, DanceSettings
from eve.dance.dance_state import DanceState, DanceStateMachine
from eve.dance.demo_source import DemoMusicSource
from eve.dance.movement_library import MoveContext, build_library

DT = 1 / 60


def music(
    intensity: float, energy: float, bpm: float = 120.0, confidence: float = 0.9, phase: float = 0.0
) -> AudioFeatures:
    return AudioFeatures(
        energy=energy,
        intensity=intensity,
        music_activity=1.0,
        is_silent=False,
        tempo_bpm=bpm if confidence > 0 else 0.0,
        tempo_confidence=confidence,
        beat_period=60.0 / bpm if confidence > 0 else 0.0,
        beat_phase=phase,
    )


def run(controller: DanceController, features: AudioFeatures, seconds: float, events_every: float = 0.0):
    out = None
    t = 0.0
    next_event = 0.0
    while t < seconds:
        events = []
        if events_every and t >= next_event:
            events = [PulseEvent(PulseKind.BEAT, t, 0.8, 0.8)]
            next_event += events_every
        out = controller.update(DT, features, 0.0, events)
        t += DT
    return out


def test_starts_idle_and_starts_dancing_with_music() -> None:
    dc = DanceController(seed=1)
    out = run(dc, SILENT_FEATURES, 1.0)
    assert out.state == DanceState.IDLE and out.weight < 0.01
    out = run(dc, music(0.3, 0.4), 3.0)
    assert dc.fsm.effective in (DanceState.CALM, DanceState.GROOVE)
    assert out.weight > 0.5
    assert out.movement


def test_energetic_music_reaches_energetic_state() -> None:
    dc = DanceController(seed=2)
    run(dc, music(0.95, 0.95, bpm=140), 12.0)
    assert dc.fsm.effective == DanceState.ENERGETIC


def test_calm_music_stays_calm() -> None:
    dc = DanceController(seed=3)
    run(dc, music(0.1, 0.3, bpm=80), 15.0)
    assert dc.fsm.effective == DanceState.CALM


def test_silence_returns_to_idle_gradually() -> None:
    dc = DanceController(seed=4)
    run(dc, music(0.6, 0.7), 8.0)
    weights = []
    for _ in range(int(10 / DT)):
        weights.append(dc.update(DT, SILENT_FEATURES, 0.0, []).weight)
    assert dc.fsm.effective == DanceState.IDLE
    assert weights[int(1 / DT)] > 0.4  # still visibly dancing one second in
    assert weights[-1] < 0.02
    # gradual: no frame-to-frame drop larger than a few percent
    assert np.max(np.abs(np.diff(weights))) < 0.05


def test_stale_features_are_treated_as_silence() -> None:
    dc = DanceController(seed=5)
    run(dc, music(0.6, 0.7), 6.0)
    for _ in range(int(5 / DT)):
        dc.update(DT, music(0.6, 0.7), features_age=5.0, events=[])
    assert dc.fsm.effective == DanceState.IDLE


def test_low_beat_confidence_falls_back_to_free_clock() -> None:
    dc = DanceController(seed=6)
    out = run(dc, music(0.5, 0.6, confidence=0.1), 4.0)
    assert out.beat_locked is False
    out = run(dc, music(0.5, 0.6, confidence=0.9), 2.0)
    assert out.beat_locked is True
    assert dc.tempo_bpm == pytest.approx(120.0, rel=0.05)


def test_clock_phase_locks_to_beat_phase() -> None:
    dc = DanceController(seed=7)
    period = 0.5
    t = 0.0
    for _ in range(int(8 / DT)):
        phase = (t / period) % 1.0
        dc.update(DT, music(0.5, 0.6, bpm=120, phase=phase), 0.0, [])
        t += DT
    clock_phase = dc.beat_pos % 1.0
    true_phase = (t / period) % 1.0
    diff = (clock_phase - true_phase + 0.5) % 1.0 - 0.5
    assert abs(diff) < 0.05


def test_beats_produce_accent_impulses_only_when_dancing() -> None:
    dc = DanceController(seed=8)
    idle = dc.update(DT, SILENT_FEATURES, 0.0, [PulseEvent(PulseKind.BEAT, 0.0, 1.0, 1.0)])
    assert idle.impulses == []
    run(dc, music(0.6, 0.7), 5.0)
    out = dc.update(DT, music(0.6, 0.7), 0.0, [PulseEvent(PulseKind.BEAT, 0.0, 1.0, 1.0)])
    channels = {ch for ch, _ in out.impulses}
    assert Ch.ROOT_Z in channels and Ch.HEAD_P in channels


def test_surge_triggers_a_single_flourish() -> None:
    dc = DanceController(seed=9)
    run(dc, music(0.6, 0.7), 8.0)
    dc.update(DT, music(0.6, 0.7), 0.0, [PulseEvent(PulseKind.SURGE, 0.0, 1.0, 1.0)])
    assert dc.fsm.effective == DanceState.FLOURISH
    seen = []
    for _ in range(int(8 / DT)):
        out = dc.update(DT, music(0.6, 0.7), 0.0, [])
        seen.append((dc.fsm.effective, out.movement))
    flourish_moves = {m for s, m in seen if s == DanceState.FLOURISH}
    assert flourish_moves <= {"celebratory_flourish", "star_burst"}
    assert dc.fsm.effective != DanceState.FLOURISH


def test_choreography_is_varied_and_avoids_immediate_repeats() -> None:
    choreo = Choreographer(build_library(), random.Random(11), phrase_probability=0.0)
    picks = [choreo.choose(DanceState.GROOVE, 0.6, now=i * 2.0).name for i in range(60)]
    counts = Counter(picks)
    assert len(counts) >= 6
    repeats = sum(1 for a, b in zip(picks, picks[1:], strict=False) if a == b)
    assert repeats <= 3
    assert counts.most_common(1)[0][1] < 0.35 * len(picks)


def test_cooldowns_are_respected() -> None:
    choreo = Choreographer(build_library(), random.Random(12))
    spins = [i * 2.0 for i in range(100) if choreo.choose(DanceState.ENERGETIC, 0.9, now=i * 2.0).name == "small_spin"]
    assert all(b - a >= 12.0 for a, b in zip(spins, spins[1:], strict=False))


def test_reduced_motion_excludes_spins_and_scales_motion() -> None:
    choreo = Choreographer(build_library(), random.Random(13))
    picks = {choreo.choose(DanceState.ENERGETIC, 0.9, now=i * 20.0, reduced_motion=True).name for i in range(80)}
    assert "small_spin" not in picks and "celebratory_flourish" not in picks
    normal = DanceController(DanceSettings(reduced_motion=False), seed=14)
    reduced = DanceController(DanceSettings(reduced_motion=True), seed=14)
    a = run(normal, music(0.7, 0.8), 6.0).targets.copy()
    b = run(reduced, music(0.7, 0.8), 6.0).targets.copy()
    posture = [Ch.ROOT_X, Ch.ROOT_Z, Ch.BODY_R, Ch.BODY_P]
    assert np.abs(b[posture]).sum() <= np.abs(a[posture]).sum() + 1e-9


@pytest.mark.parametrize("name", sorted(build_library()))
def test_every_movement_is_finite_and_starts_near_rest(name: str) -> None:
    move = build_library()[name]
    out = np.zeros(len(Ch))
    for beat in np.linspace(0.0, move.beats, 200):
        ctx = MoveContext(beat=beat, phase=beat % 1.0, amp=1.0, side=1.0, energy=0.7, length=move.beats)
        move.evaluate(ctx, out)
        assert np.isfinite(out).all()
    move.evaluate(MoveContext(0.0, 0.0, 1.0, 1.0, 0.7, move.beats), out)
    assert abs(out[Ch.ROOT_H]) < 30.0  # turns/spins begin from the current facing


def test_manual_movement_plays_without_music() -> None:
    dc = DanceController(seed=15)
    assert dc.request_movement("arm_wave")
    out = run(dc, SILENT_FEATURES, 1.0)
    assert out.movement == "arm_wave" and out.weight > 0.5
    assert dc.request_movement("does_not_exist") is False


def test_state_machine_hysteresis_prevents_flicker() -> None:
    fsm = DanceStateMachine()
    for _ in range(120):
        fsm.update(DT, 1.0, 0.3)
    changes = fsm.changes
    for i in range(600):  # drive oscillating around the groove threshold
        fsm.update(DT, 1.0, 0.42 + (0.03 if (i // 30) % 2 else -0.03))
    assert fsm.changes - changes <= 1


def test_demo_song_drives_full_pipeline_smoothly() -> None:
    src = DemoMusicSource()
    dc = DanceController(seed=16)
    anim = AnimationController(seed=16)
    prev = None
    states = set()
    for _ in range(int(src.length / DT)):
        features, events = src.update(DT)
        out = dc.update(DT, features, 0.0, events)
        pose = anim.update(DT, out)
        states.add(dc.fsm.effective)
        assert np.isfinite(pose).all()
        if prev is not None:
            jump = np.abs(pose - prev)
            jump[Ch.ROOT_H] = abs((pose[Ch.ROOT_H] - prev[Ch.ROOT_H] + 180) % 360 - 180)
            jump[Ch.EYE_OPEN] = 0  # blinks are intentionally fast
            assert jump[[Ch.ROOT_X, Ch.ROOT_Y, Ch.ROOT_Z]].max() < 0.05
            assert jump[[Ch.BODY_P, Ch.BODY_R, Ch.HEAD_P, Ch.HEAD_R]].max() < 8.0
        prev = pose.copy()
    assert {DanceState.IDLE, DanceState.CALM, DanceState.GROOVE, DanceState.ENERGETIC} <= states


def test_library_has_enough_variety_per_state() -> None:
    library = build_library()
    assert len(library) >= 27
    for state, minimum in ((DanceState.CALM, 7), (DanceState.GROOVE, 14), (DanceState.ENERGETIC, 12)):
        assert sum(1 for m in library.values() if m.states.get(state, 0) > 0) >= minimum
    assert sum(1 for m in library.values() if m.states.get(DanceState.FLOURISH, 0) > 0) >= 2


def test_phrases_mirror_moves_and_stay_varied() -> None:
    choreo = Choreographer(build_library(), random.Random(21), phrase_probability=1.0)
    picks = []
    for i in range(80):
        move = choreo.choose(DanceState.GROOVE, 0.6, now=i * 2.0)
        picks.append((move.name, choreo.choose_side(), choreo.in_phrase))
    mirrored = sum(
        1
        for (a, sa, _), (b, sb, in_phrase) in zip(picks, picks[1:], strict=False)
        if in_phrase and a == b and sa == -sb
    )
    assert mirrored >= 5  # call-and-response repeats happen, on the opposite side
    assert sum(1 for _, _, p in picks if p) > 20
    names = Counter(name for name, _, _ in picks)
    assert len(names) >= 8 and names.most_common(1)[0][1] < 0.3 * len(picks)


def test_phrase_is_abandoned_when_state_changes() -> None:
    choreo = Choreographer(build_library(), random.Random(22), phrase_probability=1.0)
    first = choreo.choose(DanceState.GROOVE, 0.6, now=0.0)
    choreo.choose_side()
    nxt = choreo.choose(DanceState.CALM, 0.2, now=2.0)
    assert nxt.states.get(DanceState.CALM, 0) > 0
    assert first is not None and not choreo.in_phrase


def test_surge_makes_eyes_wide() -> None:
    dc = DanceController(seed=23)
    run(dc, music(0.6, 0.7), 8.0)
    base = dc.update(DT, music(0.6, 0.7), 0.0, []).targets[Ch.EYE_OPEN]
    dc.update(DT, music(0.6, 0.7), 0.0, [PulseEvent(PulseKind.SURGE, 0.0, 1.0, 1.0)])
    peak = max(dc.update(DT, music(0.6, 0.7), 0.0, []).targets[Ch.EYE_OPEN] for _ in range(40))
    assert peak > base + 0.2


def test_robot_gets_sleepy_after_long_silence_and_wakes_with_music() -> None:
    anim = AnimationController(seed=24)
    dc = DanceController(seed=24)
    for _ in range(int(100 / DT)):
        anim.update(DT, dc.update(DT, SILENT_FEATURES, 0.0, []))
    assert anim.drowsiness > 0.8
    sleepy_eyes = anim.pose[Ch.EYE_OPEN]
    assert sleepy_eyes < 0.75
    for _ in range(int(6 / DT)):
        anim.update(DT, dc.update(DT, music(0.6, 0.7), 0.0, []))
    assert anim.drowsiness < 0.2
    anim.poke()
    assert anim.quiet_time == 0.0
