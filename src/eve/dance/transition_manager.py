"""Crossfades between consecutive movements so changes never pop.

The outgoing movement keeps running while its weight fades out (quintic easing); angles
are blended along the shortest arc so a finished 360° spin never unwinds.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eve.animation.interpolation import smootherstep
from eve.character.character_rig import N_CHANNELS, Ch
from eve.dance.movement_library import MoveContext, Movement


@dataclass
class ActiveMove:
    movement: Movement
    start_beat: float
    side: float
    amp_jitter: float = 1.0
    speed: float = 1.0  # 0.5 = half-time

    def local_beat(self, beat_pos: float) -> float:
        return (beat_pos - self.start_beat) * self.speed

    def finished(self, beat_pos: float) -> bool:
        return self.local_beat(beat_pos) >= self.movement.beats

    def evaluate(self, beat_pos: float, phase: float, amp: float, energy: float, out: np.ndarray) -> np.ndarray:
        ctx = MoveContext(
            beat=self.local_beat(beat_pos),
            phase=(phase * self.speed) % 1.0 if self.speed != 1.0 else phase,
            amp=amp * self.amp_jitter,
            side=self.side,
            energy=energy,
            length=self.movement.beats,
        )
        return self.movement.evaluate(ctx, out)


def _wrap(a: np.ndarray | float) -> np.ndarray | float:
    return (a + 180.0) % 360.0 - 180.0


class TransitionManager:
    def __init__(self) -> None:
        self.current: ActiveMove | None = None
        self.previous: ActiveMove | None = None
        self._blend_time = 0.0
        self._blend_elapsed = 0.0
        self._a = np.zeros(N_CHANNELS)
        self._b = np.zeros(N_CHANNELS)
        self.output = np.zeros(N_CHANNELS)

    def start(self, move: ActiveMove, blend_seconds: float | None = None) -> None:
        self.previous = self.current
        self.current = move
        self._blend_time = move.movement.blend_in if blend_seconds is None else blend_seconds
        self._blend_elapsed = 0.0

    def clear(self) -> None:
        self.current = None
        self.previous = None

    @property
    def blending(self) -> bool:
        return self.previous is not None and self._blend_elapsed < self._blend_time

    def evaluate(self, dt: float, beat_pos: float, phase: float, amp: float, energy: float) -> np.ndarray:
        out = self.output
        if self.current is None:
            out.fill(0.0)
            return out
        self.current.evaluate(beat_pos, phase, amp, energy, self._b)
        self._b[Ch.ROOT_H] = _wrap(self._b[Ch.ROOT_H])
        self._blend_elapsed += dt
        if self.previous is None or self._blend_elapsed >= self._blend_time:
            self.previous = None
            out[:] = self._b
            return out
        w = smootherstep(self._blend_elapsed / max(self._blend_time, 1e-6))
        self.previous.evaluate(beat_pos, phase, amp, energy, self._a)
        a_h = _wrap(self._a[Ch.ROOT_H])
        out[:] = self._a + (self._b - self._a) * w
        out[Ch.ROOT_H] = _wrap(a_h + _wrap(self._b[Ch.ROOT_H] - a_h) * w)
        return out
