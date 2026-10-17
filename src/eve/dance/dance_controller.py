"""Music-aware choreography: audio features in, high-level motion targets out.

Responsibilities:
* a musical clock (beat position) that phase-locks to tracked beats when tempo is
  trusted, and free-runs at a gentle pace when it is not (energy-reactive fallback);
* the dance state machine (IDLE / CALM / GROOVE / ENERGETIC / FLOURISH / TRANSITION);
* choosing, crossfading and evaluating movement primitives;
* turning beats/onsets into physical accents (spring impulses) rather than moving the
  body in proportion to loudness;
* fading the whole dance layer in and out so silence settles gradually into idle.

It knows nothing about rendering or audio capture.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field

import numpy as np

from eve.animation.interpolation import bell
from eve.audio.audio_features import SILENT_FEATURES, AudioFeatures, PulseEvent, PulseKind
from eve.character.character_rig import N_CHANNELS, Ch
from eve.dance.choreography import Choreographer
from eve.dance.dance_state import DanceState, DanceStateMachine
from eve.dance.motion_parameters import REDUCED_MOTION_SCALE
from eve.dance.motion_smoothing import ExpSmoother
from eve.dance.movement_library import Movement, build_library
from eve.dance.transition_manager import ActiveMove, TransitionManager

log = logging.getLogger(__name__)

STALE_FEATURES_SECONDS = 0.6
MIN_TEMPO_CONFIDENCE = 0.35
ONSET_ACCENT_COOLDOWN = 0.14
SURPRISE_SECONDS = 0.9


@dataclass
class DanceSettings:
    intensity: float = 1.0  # user "dance intensity" 0..1.5
    reduced_motion: bool = False
    style: str = "mixed"  # key of movement_library.DANCE_STYLES


@dataclass
class DanceOutput:
    targets: np.ndarray  # pose offsets from the relaxed pose
    weight: float  # 0..1 dance layer weight (0 = pure idle)
    impulses: list[tuple[int, float]] = field(default_factory=list)  # (channel, Δvelocity)
    state: DanceState = DanceState.IDLE
    movement: str = ""
    drive: float = 0.0
    beat_locked: bool = False
    beat_position: float = 0.0


def _wrap_phase(x: float) -> float:
    """Wrap a phase difference to [-0.5, 0.5)."""
    return (x + 0.5) % 1.0 - 0.5


class DanceController:
    def __init__(
        self,
        settings: DanceSettings | None = None,
        library: dict[str, Movement] | None = None,
        seed: int | None = None,
    ) -> None:
        self.settings = settings or DanceSettings()
        self.library = library or build_library()
        self.rng = random.Random(seed)
        self.choreographer = Choreographer(self.library, self.rng)
        self.fsm = DanceStateMachine()
        self.transitions = TransitionManager()
        self.now = 0.0
        self.beat_pos = 0.0
        self.period = 60.0 / 96.0
        self.beat_locked = False
        self._energy = ExpSmoother(0.8, 2.0)
        self._drive = ExpSmoother(1.0, 2.5)
        self._weight = ExpSmoother(0.7, 2.2)
        self._amp = ExpSmoother(1.0, 1.5, 0.6)
        self._targets = np.zeros(N_CHANNELS)
        self._last_onset_accent = -1e9
        self._accent_flip = 1.0
        self._manual: ActiveMove | None = None
        self._last_effective = DanceState.IDLE
        self._since_surge = 1e9

    # -- public ---------------------------------------------------------------------------
    def request_movement(self, name: str) -> bool:
        """Play one movement now (debug panel / demo), even without music."""
        move = self.library.get(name)
        if move is None:
            return False
        active = ActiveMove(move, self.beat_pos, self.choreographer.choose_side())
        self._manual = active
        self.transitions.start(active, 0.4)
        return True

    def update(
        self,
        dt: float,
        features: AudioFeatures = SILENT_FEATURES,
        features_age: float = 0.0,
        events: list[PulseEvent] | None = None,
    ) -> DanceOutput:
        events = events or []
        self.now += dt
        stale = features_age > STALE_FEATURES_SECONDS
        f = SILENT_FEATURES if stale else features

        activity = f.music_activity
        energy = self._energy.update(f.energy, dt)
        tempo_factor = 0.0
        if f.has_tempo and f.tempo_confidence >= MIN_TEMPO_CONFIDENCE:
            tempo_factor = min(1.0, max(0.0, (f.tempo_bpm - 80.0) / 80.0))
        raw_drive = 0.45 * f.intensity + 0.35 * energy + 0.2 * tempo_factor
        drive = self._drive.update(min(1.0, raw_drive), dt)

        self._advance_clock(dt, f, features_age, drive)

        surge = any(e.kind == PulseKind.SURGE for e in events)
        self._since_surge = 0.0 if surge else self._since_surge + dt
        self.fsm.update(dt, activity, drive, surge)
        effective = self.fsm.effective

        # A finished flourish ends the FLOURISH state before a new movement is chosen.
        current = self.transitions.current
        if effective == DanceState.FLOURISH and current is not None and current.finished(self.beat_pos):
            self.fsm.flourish_done()
            effective = self.fsm.effective

        manual_active = self._manual is not None and not self._manual.finished(self.beat_pos)
        if self._manual is not None and not manual_active:
            self._manual = None

        dancing = effective != DanceState.IDLE
        weight_target = activity if dancing else 0.0
        if manual_active:
            weight_target = 1.0
        # A move played by hand (debug panel / demo) fades in faster than music does, so it
        # is shown at full size from its first beat.
        weight = self._weight.update(weight_target, dt * (3.0 if manual_active else 1.0))
        amp = self._amp.update((0.45 + 0.75 * drive) * self.settings.intensity, dt)
        if manual_active and not dancing:
            amp = max(amp, 0.8 * self.settings.intensity)

        if not manual_active:
            self._update_movement(effective, drive)
        if not dancing and weight < 0.02 and not manual_active:
            self.transitions.clear()

        phase = self.beat_pos % 1.0
        targets = self.transitions.evaluate(dt, self.beat_pos, phase, amp, drive)
        out = self._targets
        out[:] = targets
        # Expression layered on top of the movement (bass makes the eyes glow a little).
        out[Ch.EYE_GLOW] += 0.25 * f.bass_pulse
        if self._since_surge < SURPRISE_SECONDS:
            # Wide-eyed "whoa!" when the music suddenly gets bigger.
            env = bell(self._since_surge / SURPRISE_SECONDS)
            out[Ch.EYE_OPEN] += 0.3 * env
            out[Ch.HEAD_LIFT] += 0.04 * env
            out[Ch.EYE_HAPPY] *= 1.0 - env
            out[Ch.EYE_GLOW] += 0.3 * env
        if effective == DanceState.FLOURISH:
            out[Ch.EYE_HAPPY] = max(out[Ch.EYE_HAPPY], 1.0)
        reduced = self.settings.reduced_motion
        if reduced:
            for ch in Ch:
                if ch not in (Ch.EYE_OPEN, Ch.EYE_HAPPY, Ch.EYE_LOOK_X, Ch.EYE_LOOK_Y, Ch.EYE_GLOW):
                    out[ch] *= REDUCED_MOTION_SCALE

        impulses = self._accents(events, effective, weight, amp, reduced)
        current = self.transitions.current
        self._last_effective = effective
        return DanceOutput(
            targets=out,
            weight=weight,
            impulses=impulses,
            state=self.fsm.state,
            movement=current.movement.name if current is not None else "",
            drive=drive,
            beat_locked=self.beat_locked,
            beat_position=self.beat_pos,
        )

    # -- internals ------------------------------------------------------------------------
    def _advance_clock(self, dt: float, f: AudioFeatures, age: float, drive: float) -> None:
        target_phase = None
        if f.has_tempo and f.tempo_confidence >= MIN_TEMPO_CONFIDENCE:
            period = f.beat_period
            target_phase = (f.beat_phase + age / period) % 1.0
            self.beat_locked = True
        else:
            # No trustworthy beat: pace movements gently instead of faking a beat.
            period = 60.0 / (84.0 + 36.0 * drive)
            self.beat_locked = False
        self.period += (period - self.period) * min(1.0, dt * 2.0)
        advance = dt / self.period
        self.beat_pos += advance
        if target_phase is not None:
            error = _wrap_phase(target_phase - (self.beat_pos % 1.0))
            # Never correct by more than half a frame's advance: the clock always moves
            # forward (moves never freeze or rewind), even if the phase input is bad.
            limit = 0.5 * advance
            self.beat_pos += max(-limit, min(limit, error * min(1.0, dt * 4.0)))

    def _update_movement(self, effective: DanceState, drive: float) -> None:
        current = self.transitions.current
        state_changed = effective != self._last_effective and effective != DanceState.IDLE
        if effective == DanceState.IDLE:
            return
        needs_new = current is None or current.finished(self.beat_pos) or state_changed
        if not needs_new:
            return
        self.choreographer.style = self.settings.style
        move = self.choreographer.choose(effective, drive, self.now, self.settings.reduced_motion)
        if move is None:
            return
        speed = 1.0
        if move.half_time_ok and effective == DanceState.CALM and 60.0 / self.period > 105.0:
            speed = 0.5  # calm passage at a quick tempo: dance in half-time
        active = ActiveMove(
            move,
            start_beat=self.beat_pos,
            side=self.choreographer.choose_side(),
            amp_jitter=self.rng.uniform(0.88, 1.1),
            speed=speed,
        )
        log.debug(
            "move %s (%s, side %+.0f, %s)",
            move.name,
            effective.value,
            active.side,
            "phrase" if self.choreographer.in_phrase else "pick",
        )
        blend = move.blend_in if not state_changed else max(move.blend_in, 0.7)
        self.transitions.start(active, blend)

    def _accents(
        self,
        events: list[PulseEvent],
        state: DanceState,
        weight: float,
        amp: float,
        reduced: bool,
    ) -> list[tuple[int, float]]:
        impulses: list[tuple[int, float]] = []
        if state == DanceState.IDLE or weight < 0.05:
            return impulses
        scale = weight * amp * (0.4 if reduced else 1.0)
        calm = state == DanceState.CALM
        for event in events:
            if event.kind == PulseKind.BEAT:
                if calm and event.strength < 0.6:
                    continue
                k = scale * event.strength * (0.5 + 0.5 * event.bass) * (0.5 if calm else 1.0)
                impulses += [(Ch.ROOT_Z, -0.45 * k), (Ch.BODY_SQUASH, -0.9 * k), (Ch.HEAD_P, 55.0 * k)]
            elif event.kind == PulseKind.ONSET:
                if self.now - self._last_onset_accent < ONSET_ACCENT_COOLDOWN:
                    continue
                self._last_onset_accent = self.now
                k = scale * event.strength
                if not self.beat_locked:
                    # Energy-reactive fallback: transients drive small bounces directly.
                    k *= 0.6 * (0.5 + 0.5 * event.bass)
                    impulses += [(Ch.ROOT_Z, -0.35 * k), (Ch.BODY_SQUASH, -0.6 * k), (Ch.HEAD_P, 35.0 * k)]
                elif event.bass < 0.5:
                    # Off-beat percussion while locked: a subtle alternating head tilt.
                    self._accent_flip = -self._accent_flip
                    impulses.append((Ch.HEAD_R, 30.0 * k * self._accent_flip))
        return impulses

    @property
    def tempo_bpm(self) -> float:
        return 60.0 / self.period if self.period > 0 else 0.0

    @staticmethod
    def beat_flash(beat_pos: float) -> float:
        """1 right on a beat, decaying to 0 — handy for debug visuals."""
        return math.exp(-(beat_pos % 1.0) * 8.0)
