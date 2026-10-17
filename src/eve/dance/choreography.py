"""Movement selection: weighted, history-aware, cooldown-respecting controlled randomness.

Besides single picks, the choreographer sometimes plans a short *phrase* the way human
dancers build combinations: a move, the same move mirrored ("call and response"), a
contrasting move, sometimes a return. Phrases use only short moves, are dropped as soon
as the dance state changes, and still go through the history, so they add musical
structure without making the dance repetitive.
"""

from __future__ import annotations

import math
import random
from collections import deque

from eve.dance.dance_state import DanceState
from eve.dance.movement_history import MovementHistory
from eve.dance.movement_library import Movement

REPEAT_PENALTY = 0.35  # per occurrence in the last few picks
IMMEDIATE_REPEAT_PENALTY = 0.15
PHRASE_PROBABILITY = 0.4
PHRASE_MAX_BEATS = 4  # only short moves form phrases
PHRASE_MAX_COOLDOWN = 8.0  # "special" moves (spins, big dips) keep their cooldown: never phrased
# Letters after the opening move: "A" = same move mirrored, "a" = same move same side,
# "B" = a contrasting move, "b" = the contrasting move mirrored.
PHRASE_PATTERNS = ("AB", "ABA", "BbA", "AaB")


class Choreographer:
    def __init__(
        self,
        library: dict[str, Movement],
        rng: random.Random | None = None,
        phrase_probability: float = PHRASE_PROBABILITY,
    ) -> None:
        self.library = library
        self.rng = rng or random.Random()
        self.history = MovementHistory()
        self.phrase_probability = phrase_probability
        self._last_side = 1.0
        self._pending_side: float | None = None
        self._queue: deque[tuple[str, float, DanceState]] = deque()
        self.in_phrase = False

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

    def _pick(
        self, state: DanceState, drive: float, now: float, reduced_motion: bool, exclude: str | None = None
    ) -> Movement | None:
        weights = self.weights(state, drive, now, reduced_motion)
        weights.pop(exclude or "", None)
        if not weights:
            # Everything is cooling down: relax cooldowns rather than freezing.
            candidates = [
                m
                for m in self.library.values()
                if m.states.get(state, 0) > 0 and (m.reduced_motion_ok or not reduced_motion) and m.name != exclude
            ]
            if not candidates:
                return None
            return min(candidates, key=lambda m: -self.history.seconds_since(m.name, now))
        names = list(weights)
        return self.library[self.rng.choices(names, [weights[n] for n in names])[0]]

    def choose(self, state: DanceState, drive: float, now: float, reduced_motion: bool = False) -> Movement | None:
        while self._queue:
            name, side, planned_for = self._queue.popleft()
            move = self.library[name]
            if planned_for == state and (move.reduced_motion_ok or not reduced_motion):
                self._pending_side = side
                self.in_phrase = True
                self.history.record(name, now)
                return move
            self._queue.clear()  # the music changed: abandon the phrase
        self.in_phrase = False
        pick = self._pick(state, drive, now, reduced_motion)
        if pick is None:
            return None
        self.history.record(pick.name, now)
        if self._phrase_eligible(pick) and state != DanceState.FLOURISH and self.rng.random() < self.phrase_probability:
            self._plan_phrase(pick, state, drive, now, reduced_motion)
        return pick

    @staticmethod
    def _phrase_eligible(move: Movement) -> bool:
        return move.beats <= PHRASE_MAX_BEATS and move.cooldown < PHRASE_MAX_COOLDOWN

    def _plan_phrase(self, first: Movement, state: DanceState, drive: float, now: float, reduced_motion: bool) -> None:
        contrast = self._pick(state, drive, now, reduced_motion, exclude=first.name)
        if contrast is None or not self._phrase_eligible(contrast):
            return
        side_a = self.choose_side()
        self._pending_side = side_a
        side_b = self.rng.choice((-1.0, 1.0))
        steps = {
            "A": (first.name, -side_a),
            "a": (first.name, side_a),
            "B": (contrast.name, side_b),
            "b": (contrast.name, -side_b),
        }
        for letter in self.rng.choice(PHRASE_PATTERNS):
            name, side = steps[letter]
            self._queue.append((name, side, state))

    def clear_phrase(self) -> None:
        self._queue.clear()
        self._pending_side = None

    def choose_side(self) -> float:
        """Phrase steps dictate their side; otherwise mostly alternate, sometimes repeat."""
        if self._pending_side is not None:
            side = self._pending_side
            self._pending_side = None
        else:
            side = -self._last_side if self.rng.random() < 0.7 else self._last_side
        self._last_side = side
        return side
