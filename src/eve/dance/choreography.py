"""Movement selection: weighted, history-aware, cooldown-respecting controlled randomness."""

from __future__ import annotations

import math
import random

from eve.dance.dance_state import DanceState
from eve.dance.movement_history import MovementHistory
from eve.dance.movement_library import Movement

REPEAT_PENALTY = 0.35  # per occurrence in the last few picks
IMMEDIATE_REPEAT_PENALTY = 0.15


class Choreographer:
    def __init__(self, library: dict[str, Movement], rng: random.Random | None = None) -> None:
        self.library = library
        self.rng = rng or random.Random()
        self.history = MovementHistory()
        self._last_side = 1.0

    def _drive_fit(self, move: Movement, drive: float) -> float:
        lo, hi = move.drive_range
        if lo <= drive <= hi:
            return 1.0
        distance = lo - drive if drive < lo else drive - hi
        return math.exp(-distance / 0.12)

    def weights(self, state: DanceState, drive: float, now: float, reduced_motion: bool) -> dict[str, float]:
        result: dict[str, float] = {}
        last = self.history.last
        for name, move in self.library.items():
            base = move.states.get(state, 0.0)
            if base <= 0 or (reduced_motion and not move.reduced_motion_ok):
                continue
            w = base * self._drive_fit(move, drive)
            w *= REPEAT_PENALTY ** self.history.count_recent(name)
            if name == last:
                w *= IMMEDIATE_REPEAT_PENALTY
            if self.history.seconds_since(name, now) < move.cooldown:
                w *= 0.0
            if w > 0:
                result[name] = w
        return result

    def choose(self, state: DanceState, drive: float, now: float, reduced_motion: bool = False) -> Movement | None:
        weights = self.weights(state, drive, now, reduced_motion)
        if not weights:
            # Everything is cooling down: relax cooldowns rather than freezing.
            candidates = [
                m
                for m in self.library.values()
                if m.states.get(state, 0) > 0 and (m.reduced_motion_ok or not reduced_motion)
            ]
            if not candidates:
                return None
            pick = min(candidates, key=lambda m: -self.history.seconds_since(m.name, now))
        else:
            names = list(weights)
            pick = self.library[self.rng.choices(names, [weights[n] for n in names])[0]]
        self.history.record(pick.name, now)
        return pick

    def choose_side(self) -> float:
        """Mostly alternate sides, sometimes repeat — symmetric but not mechanical."""
        side = -self._last_side if self.rng.random() < 0.7 else self._last_side
        self._last_side = side
        return side
