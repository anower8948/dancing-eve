"""Calm 'alive' behaviour: floating, breathing, blinking, glances and small tilts.

Everything here is slow and low-amplitude by design so the robot never distracts. Events
(blinks, glances) are scheduled with randomised intervals; continuous drift uses smooth
noise, never per-frame randomness.
"""

from __future__ import annotations

import math
import random

import numpy as np

from eve.animation.interpolation import bell, smootherstep
from eve.animation.procedural_motion import SmoothNoise
from eve.character.character_rig import N_CHANNELS, Ch

BLINK_DURATION = 0.17
SLEEPY_BLINK_DURATION = 0.45


class IdleAnimator:
    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self.noise = SmoothNoise(seed=self.rng.randrange(1 << 30))
        self.t = self.rng.uniform(0, 100)
        self._out = np.zeros(N_CHANNELS)
        # blink scheduler
        self._next_blink = self.rng.uniform(1.5, 4.0)
        self._blink_start: float | None = None
        self._double_blink_pending = False
        # glance scheduler: (start, duration, head_h, head_r, look_x, look_y)
        self._next_glance = self.rng.uniform(3.0, 6.0)
        self._glance: tuple[float, float, float, float, float, float] | None = None
        # mood: occasional soft content "smile" in the eyes
        self._next_mood = self.rng.uniform(8.0, 16.0)
        self._mood: tuple[float, float] | None = None
        self.blink_amount = 0.0  # 0 open .. 1 closed (applied after the springs)
        self.drowsiness = 0.0  # 0 awake .. 1 asleep-ish; set by the AnimationController
        self._breath = self.t  # breathing phase (slows down when drowsy)

    def poke(self) -> None:
        """React to a click: immediate blink and a happy look."""
        self._blink_start = self.t
        self._mood = (self.t, 2.5)

    def update(self, dt: float, drowsiness: float = 0.0) -> np.ndarray:
        self.drowsiness = drowsiness
        # Drowsy breathing slows down; integrate a separate breathing phase so the change
        # in speed never makes the motion jump.
        self.t += dt
        self._breath += dt * (1.0 - 0.45 * drowsiness)
        t = self.t
        bt = self._breath
        n = self.noise
        out = self._out
        out.fill(0.0)
        awake = 1.0 - 0.6 * drowsiness

        # Floating and breathing.
        out[Ch.ROOT_Z] = awake * (0.028 * math.sin(2 * math.pi * 0.21 * bt) + 0.01 * n.fractal(t * 0.35))
        out[Ch.BODY_SQUASH] = 0.010 * math.sin(2 * math.pi * 0.24 * bt) * (1.0 + 0.5 * drowsiness)
        out[Ch.HEAD_LIFT] = 0.008 * math.sin(2 * math.pi * 0.24 * bt - 0.9)
        # Slow drift and small orientation changes.
        out[Ch.ROOT_X] = 0.035 * n.fractal(t * 0.06 + 11.0)
        out[Ch.ROOT_H] = 9.0 * n.fractal(t * 0.045 + 23.0)
        out[Ch.BODY_R] = 2.2 * n.fractal(t * 0.11 + 5.0)
        out[Ch.BODY_P] = 1.5 * n.fractal(t * 0.09 + 41.0)
        out[Ch.HEAD_R] = 3.0 * n.fractal(t * 0.07 + 61.0)
        out[Ch.HEAD_P] = 2.0 * n.fractal(t * 0.08 + 71.0)
        out[Ch.ARM_L_SWING] = 4.0 * n.fractal(t * 0.13 + 81.0)
        out[Ch.ARM_R_SWING] = 4.0 * n.fractal(t * 0.13 + 91.0)
        out[Ch.EYE_GLOW] = 0.05 * math.sin(2 * math.pi * 0.12 * t)

        if drowsiness > 0.0:
            # Sleepy: heavy eyelids, sinking a little, head slowly nodding off.
            nod = 0.5 + 0.5 * math.sin(2 * math.pi * 0.07 * t)
            out[Ch.EYE_OPEN] -= 0.55 * drowsiness
            out[Ch.EYE_GLOW] -= 0.25 * drowsiness
            out[Ch.ROOT_Z] -= 0.05 * drowsiness
            out[Ch.HEAD_P] += drowsiness * (5.0 + 7.0 * nod)
            out[Ch.HEAD_R] += 6.0 * drowsiness
            out[Ch.ARM_L_SPREAD] -= 4.0 * drowsiness
            out[Ch.ARM_R_SPREAD] -= 4.0 * drowsiness
        if drowsiness < 0.6:
            self._update_glance(out)  # too sleepy to look around
        self._update_mood(out)
        self.blink_amount = self._update_blink()
        return out

    def _update_blink(self) -> float:
        t = self.t
        if self._blink_start is None and t >= self._next_blink:
            self._blink_start = t
        if self._blink_start is None:
            return 0.0
        duration = BLINK_DURATION + (SLEEPY_BLINK_DURATION - BLINK_DURATION) * self.drowsiness
        u = (t - self._blink_start) / duration
        if u >= 1.0:
            self._blink_start = None
            if self._double_blink_pending:
                self._double_blink_pending = False
                self._next_blink = t + 0.12
            else:
                self._double_blink_pending = self.rng.random() < 0.18
                self._next_blink = t + self.rng.uniform(2.5, 6.5) if not self._double_blink_pending else t + 0.12
            return 0.0
        # Fast close, slightly slower open.
        return smootherstep(u / 0.4) if u < 0.4 else 1.0 - smootherstep((u - 0.4) / 0.6)

    def _update_glance(self, out: np.ndarray) -> None:
        t = self.t
        if self._glance is None and t >= self._next_glance:
            side = self.rng.choice((-1.0, 1.0))
            self._glance = (
                t,
                self.rng.uniform(1.4, 3.0),
                side * self.rng.uniform(8.0, 20.0),
                side * self.rng.uniform(-6.0, 9.0),
                side * self.rng.uniform(0.3, 0.7),
                self.rng.uniform(-0.3, 0.35),
            )
        if self._glance is None:
            return
        start, duration, head_h, head_r, look_x, look_y = self._glance
        u = (t - start) / duration
        if u >= 1.0:
            self._glance = None
            self._next_glance = t + self.rng.uniform(4.0, 9.0)
            return
        # Eyes lead, head follows (head springs add the natural lag).
        w = smootherstep(u / 0.15) if u < 0.15 else 1.0 - smootherstep((u - 0.75) / 0.25) if u > 0.75 else 1.0
        out[Ch.HEAD_H] += head_h * w
        out[Ch.HEAD_R] += head_r * w
        out[Ch.EYE_LOOK_X] += look_x * w
        out[Ch.EYE_LOOK_Y] += look_y * w

    def _update_mood(self, out: np.ndarray) -> None:
        t = self.t
        if self._mood is None and t >= self._next_mood:
            self._mood = (t, self.rng.uniform(2.0, 4.0))
        if self._mood is None:
            return
        start, duration = self._mood
        u = (t - start) / duration
        if u >= 1.0:
            self._mood = None
            self._next_mood = t + self.rng.uniform(10.0, 22.0)
            return
        out[Ch.EYE_HAPPY] += 0.55 * bell(u)
