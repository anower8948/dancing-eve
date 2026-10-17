"""Reusable dance movement primitives.

Each movement writes *offsets from the relaxed pose* into a target vector for a given
musical context. They are pure functions of time (beats), so they are deterministic,
testable and can be blended freely. Smoothness, inertia and overshoot come afterwards
from the spring layer — movements describe intent, not final motion.

Conventions (see character_rig.Ch): +ROOT_X = robot moves to the viewer's right,
+BODY_R = body top leans right, +BODY_P / +HEAD_P = lean / nod forward (down),
+ARM_*_SWING = arm raised forward/up, +ARM_*_SPREAD = arm lifted outward.

To add a movement: write ``def _my_move(c: MoveContext, out: np.ndarray) -> None`` and
register a ``Movement`` in ``build_library()`` (see docs/animation-system.md).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from eve.animation.interpolation import (
    anticipate,
    bell,
    ease_out_back,
    skewed_wave,
    smootherstep,
    smoothstep,
    window,
)
from eve.character.character_rig import Ch
from eve.dance.dance_state import DanceState

TAU = 2.0 * math.pi


@dataclass(frozen=True, slots=True)
class MoveContext:
    beat: float  # beats since the movement started (already speed-scaled)
    phase: float  # phase inside the current musical beat, 0 = on the beat
    amp: float  # amplitude scale (≈0.4 calm … 1.2 energetic)
    side: float  # +1 / -1 mirror
    energy: float  # musical drive 0..1
    length: float  # movement length in beats

    @property
    def progress(self) -> float:
        return min(1.0, max(0.0, self.beat / self.length)) if self.length > 0 else 1.0


MoveFn = Callable[[MoveContext, np.ndarray], None]


@dataclass(frozen=True)
class Movement:
    name: str
    beats: float
    fn: MoveFn
    states: dict[DanceState, float]  # state -> selection weight
    drive_range: tuple[float, float] = (0.0, 1.0)
    cooldown: float = 0.0  # seconds before it may be chosen again
    reduced_motion_ok: bool = True
    half_time_ok: bool = False  # may run at half speed in calm passages
    blend_in: float = 0.45  # crossfade seconds when this movement starts

    def evaluate(self, ctx: MoveContext, out: np.ndarray) -> np.ndarray:
        out.fill(0.0)
        self.fn(ctx, out)
        return out


def hop(d: float) -> float:
    """Periodic hop: dips (weight down) on the beat, peaks mid-beat."""
    d %= 1.0
    s = math.sin(math.pi * d)
    c = math.cos(math.pi * d)
    return s * s - 0.35 * c * c


def _arms(
    out: np.ndarray, side: float, near_swing: float, near_spread: float, far_swing: float, far_spread: float
) -> None:
    """Write arm values; 'near' is the arm on the ``side`` the move leads with."""
    if side >= 0:
        out[Ch.ARM_R_SWING] += near_swing
        out[Ch.ARM_R_SPREAD] += near_spread
        out[Ch.ARM_L_SWING] += far_swing
        out[Ch.ARM_L_SPREAD] += far_spread
    else:
        out[Ch.ARM_L_SWING] += near_swing
        out[Ch.ARM_L_SPREAD] += near_spread
        out[Ch.ARM_R_SWING] += far_swing
        out[Ch.ARM_R_SPREAD] += far_spread


# ---------------------------------------------------------------------------------------
# Movements
# ---------------------------------------------------------------------------------------
def _gentle_sway(c: MoveContext, out: np.ndarray) -> None:
    cycle = 2.0 if c.energy > 0.5 else 4.0
    s = math.sin(TAU * c.beat / cycle)
    a, d = c.amp, c.side
    out[Ch.ROOT_X] = 0.07 * a * d * s
    out[Ch.BODY_R] = 9.0 * a * d * s
    out[Ch.ROOT_Z] = 0.02 * a * skewed_wave(c.phase)
    out[Ch.HEAD_R] = -3.0 * a * d * s
    out[Ch.ROOT_H] = 6.0 * a * d * s
    out[Ch.ARM_L_SWING] = 8.0 * a * s
    out[Ch.ARM_R_SWING] = -8.0 * a * s
    out[Ch.ARM_L_SPREAD] = 4.0 * a
    out[Ch.ARM_R_SPREAD] = 4.0 * a
    out[Ch.EYE_HAPPY] = 0.3


def _bob(c: MoveContext, out: np.ndarray) -> None:
    w = skewed_wave(c.phase)
    a = c.amp
    out[Ch.ROOT_Z] = 0.045 * a * w
    out[Ch.BODY_P] = -4.0 * a * w
    out[Ch.BODY_SQUASH] = -0.035 * a * max(0.0, -w) + 0.02 * a * max(0.0, w)
    out[Ch.HEAD_P] = -3.0 * a * skewed_wave(c.phase - 0.08)
    out[Ch.ROOT_H] = 10.0 * a * c.side * math.sin(TAU * c.beat / 4.0)
    swing = 10.0 * a * skewed_wave(c.phase + 0.1)
    out[Ch.ARM_L_SWING] = swing
    out[Ch.ARM_R_SWING] = swing
    out[Ch.ARM_L_SPREAD] = 5.0 * a
    out[Ch.ARM_R_SPREAD] = 5.0 * a
    out[Ch.EYE_HAPPY] = 0.35


def _double_bounce(c: MoveContext, out: np.ndarray) -> None:
    local = c.beat % 2.0
    if local < 1.0:
        h = hop(local * 2.0)
        size = 0.065
    else:
        h = hop(local - 1.0)
        size = 0.03
    a = c.amp
    out[Ch.ROOT_Z] = size * a * h
    out[Ch.BODY_SQUASH] = -0.06 * a * max(0.0, -h) + 0.04 * a * max(0.0, h)
    up = max(0.0, h)
    out[Ch.ARM_L_SWING] = 25.0 * a * up
    out[Ch.ARM_R_SWING] = 25.0 * a * up
    out[Ch.ARM_L_SPREAD] = 15.0 * a * up
    out[Ch.ARM_R_SPREAD] = 15.0 * a * up
    out[Ch.HEAD_P] = 5.0 * a * max(0.0, -h)
    out[Ch.EYE_HAPPY] = 0.6


def _alternating_bounce(c: MoveContext, out: np.ndarray) -> None:
    s = math.sin(math.pi * c.beat)  # +, -, +, - each beat
    a, d = c.amp, c.side
    out[Ch.ROOT_X] = 0.075 * a * d * s
    out[Ch.ROOT_Z] = 0.05 * a * hop(c.phase)
    out[Ch.BODY_R] = 11.0 * a * d * s
    out[Ch.HEAD_R] = -5.0 * a * d * s
    out[Ch.ROOT_H] = -8.0 * a * d * s
    lead = max(0.0, s)
    trail = max(0.0, -s)
    _arms(out, d, 10.0 * a * lead, 28.0 * a * lead + 6.0, 10.0 * a * trail, 28.0 * a * trail + 6.0)
    out[Ch.EYE_HAPPY] = 0.5
    out[Ch.EYE_LOOK_X] = 0.35 * d * s


def _head_nod(c: MoveContext, out: np.ndarray) -> None:
    nod = (1.0 - skewed_wave(c.phase)) * 0.5  # 1 on the beat
    a = c.amp
    out[Ch.HEAD_P] = 11.0 * a * nod
    out[Ch.BODY_P] = 3.0 * a * nod
    out[Ch.ROOT_Z] = -0.015 * a * nod
    out[Ch.HEAD_R] = 7.0 * a * c.side * math.sin(TAU * c.beat / 4.0)
    out[Ch.HEAD_H] = 6.0 * a * c.side * math.sin(TAU * c.beat / 8.0)
    out[Ch.EYE_HAPPY] = 0.55
    out[Ch.EYE_LOOK_Y] = -0.2 * nod


def _small_spin(c: MoveContext, out: np.ndarray) -> None:
    b, a, d = c.beat, c.amp, c.side
    turn = anticipate(window(b, 0.0, 3.3), amount=0.07, split=0.22)
    out[Ch.ROOT_H] = 360.0 * d * turn
    out[Ch.BODY_R] = 12.0 * a * d * bell(window(b, 0.7, 3.2))
    out[Ch.BODY_P] = -4.0 * a * bell(window(b, 0.6, 3.4))
    out[Ch.ROOT_Z] = 0.08 * a * bell(window(b, 0.4, 3.6))
    spread = 35.0 * a * bell(window(b, 0.6, 3.4))
    out[Ch.ARM_L_SPREAD] = spread
    out[Ch.ARM_R_SPREAD] = spread
    out[Ch.HEAD_H] = 18.0 * d * bell(window(b, 0.2, 1.4))  # head leads into the turn ("spotting")
    out[Ch.EYE_HAPPY] = 0.7


def _circular_glide(c: MoveContext, out: np.ndarray) -> None:
    th = TAU * c.beat / 8.0
    a, d = c.amp, c.side
    r = 0.09 * a
    out[Ch.ROOT_X] = r * d * math.sin(th)
    out[Ch.ROOT_Y] = 0.8 * r * (1.0 - math.cos(th))
    out[Ch.ROOT_H] = 18.0 * a * d * math.cos(th)
    out[Ch.BODY_R] = 7.0 * a * d * math.cos(th)
    out[Ch.ROOT_Z] = 0.025 * a * skewed_wave(c.phase)
    out[Ch.EYE_LOOK_X] = 0.35 * d * math.cos(th)
    out[Ch.ARM_L_SPREAD] = 10.0 * a
    out[Ch.ARM_R_SPREAD] = 10.0 * a
    out[Ch.EYE_HAPPY] = 0.4


def _arm_wave(c: MoveContext, out: np.ndarray) -> None:
    b, a, d = c.beat, c.amp, c.side
    first = bell(window(b, 0.0, 2.0))
    second = bell(window(b, 2.0, 4.0))
    wave = math.sin(TAU * b)
    _arms(
        out,
        d,
        15.0 * a * first,
        (100.0 + 30.0 * min(a, 1.0) + 18.0 * wave) * first,
        15.0 * a * second,
        (100.0 + 30.0 * min(a, 1.0) + 18.0 * wave) * second,
    )
    out[Ch.BODY_R] = -6.0 * a * d * (first - second)
    out[Ch.HEAD_R] = 8.0 * a * d * (first - second)
    out[Ch.ROOT_Z] = 0.02 * a * skewed_wave(c.phase)
    out[Ch.EYE_HAPPY] = 0.85


def _excited_wiggle(c: MoveContext, out: np.ndarray) -> None:
    b, a = c.beat, c.amp
    w = math.sin(2.0 * TAU * b)
    out[Ch.BODY_R] = 12.0 * a * w
    out[Ch.HEAD_R] = -8.0 * a * math.sin(2.0 * TAU * b - 0.5)
    out[Ch.ROOT_X] = 0.02 * a * w
    out[Ch.ROOT_Z] = 0.03 * a * hop((2.0 * b) % 1.0)
    out[Ch.ARM_L_SWING] = 20.0 * a * w
    out[Ch.ARM_R_SWING] = -20.0 * a * w
    out[Ch.ARM_L_SPREAD] = 18.0 * a
    out[Ch.ARM_R_SPREAD] = 18.0 * a
    out[Ch.EYE_HAPPY] = 1.0


_ACCENT_POSES = (
    {
        Ch.BODY_P: 8.0,
        Ch.BODY_R: 8.0,
        Ch.ARM_L_SPREAD: 45.0,
        Ch.ARM_R_SPREAD: 45.0,
        Ch.ARM_L_SWING: 20.0,
        Ch.ARM_R_SWING: 20.0,
        Ch.HEAD_P: -6.0,
        Ch.ROOT_Z: -0.03,
    },
    {
        Ch.BODY_P: -5.0,
        Ch.BODY_R: -8.0,
        Ch.ARM_L_SWING: 15.0,
        Ch.ARM_R_SWING: 15.0,
        Ch.ARM_L_SPREAD: 120.0,
        Ch.ARM_R_SPREAD: 120.0,
        Ch.ROOT_Z: 0.04,
        Ch.HEAD_R: 8.0,
    },
)
_MIRRORED = (Ch.BODY_R, Ch.HEAD_R)


def _rhythmic_accent(c: MoveContext, out: np.ndarray) -> None:
    pose = _ACCENT_POSES[int(c.beat) % 2]
    snap = ease_out_back(min(1.0, c.phase / 0.3), overshoot=1.2)
    hold = 1.0 - 0.55 * smoothstep(window(c.phase, 0.55, 1.0))
    k = c.amp * snap * hold
    for ch, value in pose.items():
        out[ch] = value * k * (c.side if ch in _MIRRORED else 1.0)
    out[Ch.EYE_HAPPY] = 0.6


def _floating_turn(c: MoveContext, out: np.ndarray) -> None:
    b, a, d = c.beat, c.amp, c.side
    angle = 50.0 + 30.0 * min(1.0, a)
    out_turn = anticipate(window(b, 0.0, 3.0), amount=0.08)
    back = smootherstep(window(b, 5.0, 7.5))
    turn = out_turn * (1.0 - back)
    out[Ch.ROOT_H] = angle * d * turn
    out[Ch.HEAD_H] = -0.45 * angle * d * bell(window(b, 2.0, 6.0))  # glance back at the viewer
    out[Ch.BODY_R] = -6.0 * d * bell(window(b, 0.0, 1.0)) + 5.0 * d * bell(window(b, 1.0, 3.0))
    out[Ch.ROOT_Z] = 0.035 * a * bell(window(b, 0.5, 7.5))
    out[Ch.ARM_L_SPREAD] = 8.0 * a * bell(window(b, 0.5, 7.0))
    out[Ch.ARM_R_SPREAD] = 8.0 * a * bell(window(b, 0.5, 7.0))
    out[Ch.EYE_HAPPY] = 0.45
    out[Ch.EYE_LOOK_X] = -0.4 * d * bell(window(b, 2.0, 6.0))


def _celebratory_flourish(c: MoveContext, out: np.ndarray) -> None:
    b, a, d = c.beat, c.amp, c.side
    up = smootherstep(window(b, 0.3, 1.5)) * (1.0 - smootherstep(window(b, 4.6, 5.8)))
    out[Ch.ROOT_Z] = 0.14 * max(a, 0.7) * up
    out[Ch.BODY_SQUASH] = 0.06 * up * bell(window(b, 0.3, 2.0))
    arms = bell(window(b, 0.4, 5.4)) ** 0.6
    out[Ch.ARM_L_SWING] = 20.0 * arms
    out[Ch.ARM_R_SWING] = 20.0 * arms
    out[Ch.ARM_L_SPREAD] = 145.0 * arms
    out[Ch.ARM_R_SPREAD] = 145.0 * arms
    out[Ch.ROOT_H] = 360.0 * d * anticipate(window(b, 1.0, 3.9), amount=0.06)
    out[Ch.BODY_P] = -8.0 * up
    out[Ch.HEAD_P] = -6.0 * up
    out[Ch.EYE_HAPPY] = 1.0
    out[Ch.EYE_GLOW] = 0.45 * up


def _slow_dance(c: MoveContext, out: np.ndarray) -> None:
    th = TAU * c.beat / 8.0
    a, d = c.amp, c.side
    s = math.sin(th)
    out[Ch.ROOT_X] = 0.05 * a * d * s
    out[Ch.ROOT_H] = 22.0 * a * d * s
    out[Ch.BODY_R] = 6.0 * a * d * s
    out[Ch.HEAD_R] = 10.0 * a * d * math.sin(th + 0.8)
    out[Ch.HEAD_P] = -4.0
    out[Ch.ROOT_Z] = 0.02 * a * math.sin(TAU * c.beat / 2.0)
    out[Ch.ARM_L_SWING] = 35.0 * a
    out[Ch.ARM_R_SWING] = 35.0 * a
    out[Ch.ARM_L_SPREAD] = 10.0 * a
    out[Ch.ARM_R_SPREAD] = 10.0 * a
    out[Ch.EYE_OPEN] = -0.3  # dreamy, half-lidded
    out[Ch.EYE_HAPPY] = 0.75


def _side_step(c: MoveContext, out: np.ndarray) -> None:
    """Step-touch: a quick slide on each beat (lands early, then holds), 2 beats per side."""
    b, a, d = c.beat, c.amp, c.side
    step = int(b) % 4
    slide = smootherstep(min(1.0, c.phase / 0.35))
    positions = (1.0, 1.0, -1.0, -1.0)
    prev = positions[(step - 1) % 4] if b >= 1.0 else 0.0  # first step starts from the centre
    x = prev + (positions[step] - prev) * slide
    out[Ch.ROOT_X] = 0.08 * a * d * x
    moving = positions[step] != prev
    lean = (positions[step] - prev) * 0.5 * bell(min(1.0, c.phase / 0.6)) if moving else 0.0
    out[Ch.BODY_R] = -8.0 * a * d * lean + 4.0 * a * d * x  # lag back while sliding, lean in when landed
    out[Ch.ROOT_Z] = 0.03 * a * hop(c.phase)
    out[Ch.HEAD_R] = -4.0 * a * d * x
    out[Ch.EYE_LOOK_X] = 0.3 * d * x
    _arms(out, d * x, 12.0 * a, 22.0 * a, 4.0 * a, 6.0 * a)
    out[Ch.EYE_HAPPY] = 0.45


_POP_POSES = (
    {Ch.BODY_R: 10.0, Ch.HEAD_R: -12.0, Ch.HEAD_H: 15.0, Ch.ARM_R_SPREAD: 60.0, Ch.ARM_L_SWING: 30.0},
    {Ch.BODY_P: 8.0, Ch.HEAD_P: 10.0, Ch.ARM_L_SWING: 80.0, Ch.ARM_R_SWING: 80.0, Ch.ROOT_Z: -0.03},
    {Ch.BODY_R: -10.0, Ch.HEAD_R: 12.0, Ch.HEAD_H: -15.0, Ch.ARM_L_SPREAD: 60.0, Ch.ARM_R_SWING: 30.0},
    {Ch.ROOT_Z: 0.05, Ch.ARM_L_SPREAD: 45.0, Ch.ARM_R_SPREAD: 45.0, Ch.HEAD_P: -8.0, Ch.ROOT_H: 20.0},
)
_POP_MIRRORED = (Ch.BODY_R, Ch.HEAD_R, Ch.HEAD_H, Ch.ROOT_H)


def _robot_pop(c: MoveContext, out: np.ndarray) -> None:
    """Staccato robot dance: snap into a new held pose exactly on each beat."""
    pose = _POP_POSES[int(c.beat) % len(_POP_POSES)]
    k = c.amp * ease_out_back(min(1.0, c.phase / 0.15), overshoot=0.9)
    for ch, value in pose.items():
        out[ch] = value * k * (c.side if ch in _POP_MIRRORED else 1.0)
    out[Ch.EYE_HAPPY] = 0.3


def _body_wave(c: MoveContext, out: np.ndarray) -> None:
    """A wave travelling upward: root, then body, then head, each a little later."""
    a, d = c.amp, c.side
    th = TAU * c.beat / 2.0
    out[Ch.ROOT_Z] = 0.035 * a * math.sin(th)
    out[Ch.BODY_P] = 7.0 * a * math.sin(th - 0.9)
    out[Ch.HEAD_P] = 9.0 * a * math.sin(th - 1.8)
    out[Ch.BODY_R] = 5.0 * a * d * math.sin(th / 2.0)
    out[Ch.HEAD_R] = 6.0 * a * d * math.sin(th / 2.0 - 1.2)
    swing = 18.0 * a * math.sin(th - 2.4)
    out[Ch.ARM_L_SWING] = swing
    out[Ch.ARM_R_SWING] = swing
    out[Ch.ARM_L_SPREAD] = 10.0 * a
    out[Ch.ARM_R_SPREAD] = 10.0 * a
    out[Ch.EYE_HAPPY] = 0.5


def _headbang(c: MoveContext, out: np.ndarray) -> None:
    a = c.amp
    nod = (1.0 - skewed_wave(c.phase, peak_at=0.7)) * 0.5  # sharp drop onto the beat
    out[Ch.HEAD_P] = 22.0 * a * nod - 4.0 * a
    out[Ch.BODY_P] = 8.0 * a * nod
    out[Ch.ROOT_Z] = -0.03 * a * nod
    out[Ch.BODY_SQUASH] = -0.03 * a * nod
    out[Ch.ARM_L_SPREAD] = 20.0 * a
    out[Ch.ARM_R_SPREAD] = 20.0 * a
    out[Ch.ARM_L_SWING] = -10.0 * a * nod
    out[Ch.ARM_R_SWING] = -10.0 * a * nod
    out[Ch.EYE_OPEN] = -0.25 * nod
    out[Ch.EYE_HAPPY] = 0.7


def _fist_pump(c: MoveContext, out: np.ndarray) -> None:
    """One arm raised, pumping on every beat; switches arms halfway."""
    b, a, d = c.beat, c.amp, c.side
    pump = (1.0 - skewed_wave(c.phase, peak_at=0.55)) * 0.5
    first = bell(window(b, 0.0, 2.0)) ** 0.5
    second = bell(window(b, 2.0, 4.0)) ** 0.5
    _arms(
        out,
        d,
        15.0 * a * first,
        (110.0 + 25.0 * min(a, 1.0) + 25.0 * pump) * first,
        15.0 * a * second,
        (110.0 + 25.0 * min(a, 1.0) + 25.0 * pump) * second,
    )
    out[Ch.ROOT_Z] = 0.04 * a * hop(c.phase)
    out[Ch.BODY_R] = -5.0 * a * d * (first - second)
    out[Ch.HEAD_P] = -6.0 * a * pump
    out[Ch.EYE_HAPPY] = 0.9
    out[Ch.EYE_GLOW] = 0.15 * pump


def _hop_turn(c: MoveContext, out: np.ndarray) -> None:
    """Twist: little hops turning left/right on alternate beats."""
    a, d = c.amp, c.side
    direction = 1.0 if int(c.beat) % 2 == 0 else -1.0
    prev = -direction
    turn = prev + (direction - prev) * smootherstep(min(1.0, c.phase / 0.4))
    if c.beat < 1.0:
        turn *= smootherstep(c.beat)  # ease in from facing forward
    out[Ch.ROOT_H] = 24.0 * a * d * turn
    out[Ch.BODY_R] = -6.0 * a * d * turn
    out[Ch.ROOT_Z] = 0.045 * a * hop(c.phase)
    out[Ch.HEAD_H] = -10.0 * a * d * turn  # keep looking at the viewer
    _arms(out, d * turn, 25.0 * a, 18.0 * a, 5.0 * a, 8.0 * a)
    out[Ch.EYE_HAPPY] = 0.6


def _lean_back_groove(c: MoveContext, out: np.ndarray) -> None:
    a, d = c.amp, c.side
    lean = smootherstep(min(1.0, c.beat / 1.0)) * (1.0 - smootherstep(window(c.beat, 3.2, 4.0)))
    bob = skewed_wave(c.phase)
    out[Ch.BODY_P] = -10.0 * a * lean
    out[Ch.HEAD_P] = 6.0 * a * lean - 5.0 * a * bob * lean
    out[Ch.ROOT_Z] = 0.02 * a * bob
    out[Ch.HEAD_R] = 8.0 * a * d * lean * math.sin(TAU * c.beat / 4.0)
    out[Ch.ARM_L_SPREAD] = 28.0 * a * lean
    out[Ch.ARM_R_SPREAD] = 28.0 * a * lean
    out[Ch.ARM_L_SWING] = -15.0 * a * lean
    out[Ch.ARM_R_SWING] = -15.0 * a * lean
    out[Ch.EYE_OPEN] = -0.2 * lean
    out[Ch.EYE_HAPPY] = 0.8 * lean


def _figure_eight(c: MoveContext, out: np.ndarray) -> None:
    th = TAU * c.beat / 8.0
    a, d = c.amp, c.side
    out[Ch.ROOT_X] = 0.09 * a * d * math.sin(th)
    out[Ch.ROOT_Y] = 0.06 * a * math.sin(2.0 * th)
    out[Ch.ROOT_Z] = 0.025 * a * math.sin(2.0 * th + 0.6)
    out[Ch.BODY_R] = 9.0 * a * d * math.cos(th)
    out[Ch.ROOT_H] = 14.0 * a * d * math.cos(th)
    out[Ch.HEAD_R] = -4.0 * a * d * math.cos(th)
    out[Ch.EYE_LOOK_X] = 0.3 * d * math.cos(th)
    out[Ch.ARM_L_SPREAD] = 12.0 * a
    out[Ch.ARM_R_SPREAD] = 12.0 * a
    out[Ch.EYE_HAPPY] = 0.4


def _pendulum_swing(c: MoveContext, out: np.ndarray) -> None:
    """The body swings below a steady head, like a pendulum."""
    a, d = c.amp, c.side
    s = math.sin(TAU * c.beat / 4.0)
    out[Ch.BODY_R] = -13.0 * a * d * s
    out[Ch.ROOT_X] = 0.05 * a * d * s
    out[Ch.HEAD_R] = 9.0 * a * d * s  # counter-tilt keeps the face level
    out[Ch.ROOT_Z] = 0.02 * a * abs(s)
    out[Ch.ARM_L_SWING] = 6.0 * a * s
    out[Ch.ARM_R_SWING] = -6.0 * a * s
    out[Ch.EYE_HAPPY] = 0.35


def _look_around(c: MoveContext, out: np.ndarray) -> None:
    """Curious listening: glance to one side, then the other, with a little float."""
    b, a, d = c.beat, c.amp, c.side
    left = bell(window(b, 0.5, 3.5))
    right = bell(window(b, 4.0, 7.5))
    look = d * (left - right)
    out[Ch.HEAD_H] = 28.0 * look
    out[Ch.HEAD_R] = 7.0 * look
    out[Ch.EYE_LOOK_X] = 0.7 * look
    out[Ch.EYE_LOOK_Y] = 0.2 * (left + right)
    out[Ch.ROOT_H] = 8.0 * look
    out[Ch.ROOT_Z] = 0.03 * a * math.sin(TAU * b / 8.0)
    out[Ch.HEAD_P] = -3.0 * (left + right)


def _arm_circles(c: MoveContext, out: np.ndarray) -> None:
    """Arms swing in circles, out of phase with each other."""
    th = TAU * c.beat / 2.0
    a = c.amp
    out[Ch.ARM_L_SWING] = (45.0 + 40.0 * math.sin(th)) * a
    out[Ch.ARM_L_SPREAD] = (30.0 + 25.0 * math.cos(th)) * a
    out[Ch.ARM_R_SWING] = (45.0 + 40.0 * math.sin(th + math.pi)) * a
    out[Ch.ARM_R_SPREAD] = (30.0 + 25.0 * math.cos(th + math.pi)) * a
    out[Ch.ROOT_Z] = 0.035 * a * hop(c.phase)
    out[Ch.BODY_R] = 5.0 * a * math.sin(th)
    out[Ch.EYE_HAPPY] = 0.85


def _shimmy(c: MoveContext, out: np.ndarray) -> None:
    """Fast, small shoulder shake (four per beat) with arms out."""
    a = c.amp
    shake = math.sin(4.0 * TAU * c.beat)
    out[Ch.BODY_R] = 4.5 * a * shake
    out[Ch.ROOT_H] = 6.0 * a * shake
    out[Ch.HEAD_R] = -3.0 * a * shake
    out[Ch.ROOT_Z] = 0.015 * a * skewed_wave(c.phase)
    out[Ch.ARM_L_SPREAD] = 35.0 * a
    out[Ch.ARM_R_SPREAD] = 35.0 * a
    out[Ch.ARM_L_SWING] = 15.0 * a
    out[Ch.ARM_R_SWING] = 15.0 * a
    out[Ch.EYE_HAPPY] = 1.0


def _dip_and_rise(c: MoveContext, out: np.ndarray) -> None:
    """Sink low over two beats (anticipation), burst up on beat three, settle."""
    b, a = c.beat, c.amp
    dip = smootherstep(window(b, 0.0, 2.0)) * (1.0 - smootherstep(window(b, 2.0, 2.3)))
    rise = ease_out_back(window(b, 2.0, 2.5), overshoot=1.1) * (1.0 - smootherstep(window(b, 3.0, 4.0)))
    out[Ch.ROOT_Z] = -0.09 * a * dip + 0.11 * a * rise
    out[Ch.BODY_SQUASH] = -0.06 * a * dip + 0.05 * a * rise
    out[Ch.BODY_P] = 6.0 * a * dip - 5.0 * a * rise
    out[Ch.HEAD_P] = 8.0 * a * dip - 8.0 * a * rise
    out[Ch.ARM_L_SWING] = -15.0 * a * dip + 15.0 * a * rise
    out[Ch.ARM_R_SWING] = -15.0 * a * dip + 15.0 * a * rise
    out[Ch.ARM_L_SPREAD] = (105.0 + 30.0 * min(a, 1.0)) * rise
    out[Ch.ARM_R_SPREAD] = (105.0 + 30.0 * min(a, 1.0)) * rise
    out[Ch.EYE_HAPPY] = 0.9 * rise
    out[Ch.EYE_OPEN] = 0.2 * rise


def _star_burst(c: MoveContext, out: np.ndarray) -> None:
    """Flourish: crouch, burst into a star (arms wide), slow half turn and back."""
    b, a, d = c.beat, c.amp, c.side
    crouch = bell(window(b, 0.0, 1.0))
    star = smootherstep(window(b, 0.8, 1.4)) * (1.0 - smootherstep(window(b, 4.8, 6.0)))
    out[Ch.ROOT_Z] = -0.06 * crouch + 0.12 * max(a, 0.7) * star
    out[Ch.BODY_SQUASH] = -0.05 * crouch + 0.05 * star
    out[Ch.ARM_L_SPREAD] = 115.0 * star
    out[Ch.ARM_R_SPREAD] = 115.0 * star
    out[Ch.ARM_L_SWING] = 10.0 * star
    out[Ch.ARM_R_SWING] = 10.0 * star
    out[Ch.ROOT_H] = 150.0 * d * bell(window(b, 1.2, 5.2))
    out[Ch.HEAD_H] = -40.0 * d * bell(window(b, 1.4, 5.0))  # keeps glancing back at you
    out[Ch.HEAD_P] = -8.0 * star
    out[Ch.EYE_HAPPY] = 1.0
    out[Ch.EYE_GLOW] = 0.5 * star


C, G, E, F = DanceState.CALM, DanceState.GROOVE, DanceState.ENERGETIC, DanceState.FLOURISH


def build_library() -> dict[str, Movement]:
    moves = [
        Movement("gentle_sway", 4, _gentle_sway, {C: 3.0, G: 1.2}, (0.0, 0.6), 0.0, True, True, 0.8),
        Movement("bob", 4, _bob, {G: 3.0, E: 1.5}, (0.25, 0.9), 0.0, True, False, 0.45),
        Movement("double_bounce", 2, _double_bounce, {G: 1.5, E: 2.5}, (0.4, 1.0), 3.0, True, False, 0.35),
        Movement("alternating_bounce", 4, _alternating_bounce, {G: 2.5, E: 2.5}, (0.35, 1.0), 2.0, True, False, 0.4),
        Movement("head_nod", 4, _head_nod, {C: 1.5, G: 1.5}, (0.1, 0.7), 2.0, True, True, 0.5),
        Movement("small_spin", 4, _small_spin, {G: 0.6, E: 1.4}, (0.45, 1.0), 12.0, False, False, 0.4),
        Movement("circular_glide", 8, _circular_glide, {C: 1.5, G: 1.2}, (0.1, 0.7), 8.0, True, True, 0.8),
        Movement("arm_wave", 4, _arm_wave, {G: 1.5, E: 1.5}, (0.3, 1.0), 6.0, True, False, 0.5),
        Movement("excited_wiggle", 2, _excited_wiggle, {E: 2.5}, (0.6, 1.0), 4.0, True, False, 0.3),
        Movement("rhythmic_accent", 2, _rhythmic_accent, {G: 1.5, E: 2.5}, (0.45, 1.0), 3.0, True, False, 0.3),
        Movement("floating_turn", 8, _floating_turn, {C: 1.2, G: 1.0}, (0.0, 0.7), 10.0, True, True, 0.7),
        Movement("celebratory_flourish", 6, _celebratory_flourish, {F: 1.0}, (0.0, 1.0), 0.0, False, False, 0.4),
        Movement("slow_dance", 8, _slow_dance, {C: 2.5}, (0.0, 0.45), 6.0, True, True, 1.0),
        Movement("side_step", 4, _side_step, {G: 2.0, E: 1.2}, (0.3, 0.9), 2.0, True, False, 0.4),
        Movement("robot_pop", 4, _robot_pop, {G: 1.2, E: 1.6}, (0.45, 1.0), 6.0, True, False, 0.3),
        Movement("body_wave", 4, _body_wave, {C: 0.8, G: 1.8}, (0.2, 0.8), 4.0, True, True, 0.6),
        Movement("headbang", 2, _headbang, {E: 1.8}, (0.7, 1.0), 6.0, True, False, 0.3),
        Movement("fist_pump", 4, _fist_pump, {E: 2.0, G: 0.6}, (0.6, 1.0), 6.0, True, False, 0.4),
        Movement("hop_turn", 4, _hop_turn, {G: 1.0, E: 1.8}, (0.5, 1.0), 5.0, True, False, 0.4),
        Movement("lean_back_groove", 4, _lean_back_groove, {C: 1.0, G: 1.5}, (0.15, 0.7), 5.0, True, True, 0.6),
        Movement("figure_eight", 8, _figure_eight, {C: 1.4, G: 1.0}, (0.1, 0.7), 10.0, True, True, 0.8),
        Movement("pendulum_swing", 4, _pendulum_swing, {C: 2.0, G: 0.6}, (0.0, 0.55), 3.0, True, True, 0.7),
        Movement("look_around", 8, _look_around, {C: 1.2}, (0.0, 0.4), 14.0, True, True, 0.8),
        Movement("arm_circles", 4, _arm_circles, {E: 1.5, G: 0.7}, (0.55, 1.0), 8.0, True, False, 0.4),
        Movement("shimmy", 2, _shimmy, {G: 1.0, E: 1.8}, (0.5, 1.0), 4.0, True, False, 0.3),
        Movement("dip_and_rise", 4, _dip_and_rise, {G: 1.2, E: 1.0}, (0.4, 1.0), 10.0, True, False, 0.5),
        Movement("star_burst", 6, _star_burst, {F: 1.0}, (0.0, 1.0), 0.0, False, False, 0.4),
    ]
    return {m.name: m for m in moves}
