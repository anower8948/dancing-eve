"""Dance state machine with hysteresis, minimum dwell times and cooldowns.

States describe *how* the robot dances, chosen from musical drive (rhythmic density,
loudness relative to the song, tempo) — never from loudness alone and never from an
assumed genre or emotion.

    IDLE ──music──▶ CALM ◀──▶ GROOVE ◀──▶ ENERGETIC
                      ▲          │  surge     │
                      │          └──▶ FLOURISH ◀┘ (one celebratory move, then back)
    Every change between two dancing states passes through TRANSITION (a crossfade).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DanceState(Enum):
    IDLE = "idle"
    CALM = "calm"
    GROOVE = "groove"
    ENERGETIC = "energetic"
    FLOURISH = "flourish"
    TRANSITION = "transition"


LEVELS = (DanceState.CALM, DanceState.GROOVE, DanceState.ENERGETIC)


@dataclass
class StateThresholds:
    music_on: float = 0.55  # activity needed to start dancing
    music_off: float = 0.25  # activity below which we head back to idle
    music_on_hold: float = 0.5  # seconds above music_on before leaving IDLE
    music_off_hold: float = 1.2  # seconds below music_off before returning to IDLE
    groove_enter: float = 0.42
    groove_exit: float = 0.32
    energetic_enter: float = 0.66
    energetic_exit: float = 0.55
    level_hold: float = 1.5  # drive must stay past a threshold this long
    min_dwell: float = 3.0  # minimum seconds in a level before changing again
    transition_time: float = 0.8
    flourish_cooldown: float = 15.0
    flourish_max: float = 6.0


class DanceStateMachine:
    def __init__(self, thresholds: StateThresholds | None = None) -> None:
        self.t = thresholds or StateThresholds()
        self.state = DanceState.IDLE
        self.target = DanceState.IDLE  # destination while in TRANSITION
        self.level = DanceState.CALM  # last dancing level (to return to after FLOURISH)
        self.time_in_state = 0.0
        self._timer = 0.0  # transition / flourish timer
        self._pending: DanceState | None = None
        self._pending_for = 0.0
        self._music_timer = 0.0
        self._since_flourish = 1e9
        self.changes = 0

    @property
    def effective(self) -> DanceState:
        """The state movements should be chosen for (the target while transitioning)."""
        return self.target if self.state == DanceState.TRANSITION else self.state

    def _go(self, new: DanceState) -> None:
        if new == self.effective:
            return
        self.changes += 1
        if self.state == DanceState.IDLE or new == DanceState.IDLE:
            # Entering/leaving idle is a gradual weight fade handled by the controller.
            self.state = new
            self.target = new
        else:
            self.state = DanceState.TRANSITION
            self.target = new
            self._timer = 0.0
        self.time_in_state = 0.0
        if new in LEVELS:
            self.level = new

    def _desired_level(self, drive: float) -> DanceState:
        current = self.level
        t = self.t
        if current == DanceState.CALM:
            return DanceState.GROOVE if drive > t.groove_enter else DanceState.CALM
        if current == DanceState.GROOVE:
            if drive > t.energetic_enter:
                return DanceState.ENERGETIC
            if drive < t.groove_exit:
                return DanceState.CALM
            return DanceState.GROOVE
        if drive < t.energetic_exit:
            return DanceState.GROOVE if drive > t.groove_exit else DanceState.CALM
        return DanceState.ENERGETIC

    def initial_level(self, drive: float) -> DanceState:
        if drive > self.t.energetic_enter:
            return DanceState.ENERGETIC
        if drive > self.t.groove_enter:
            return DanceState.GROOVE
        return DanceState.CALM

    def flourish_done(self) -> None:
        if self.effective == DanceState.FLOURISH:
            self._go(self.level)

    def update(self, dt: float, activity: float, drive: float, surge: bool = False) -> DanceState:
        t = self.t
        self.time_in_state += dt
        self._since_flourish += dt

        if self.state == DanceState.TRANSITION:
            self._timer += dt
            if self._timer >= t.transition_time:
                self.state = self.target

        # Music presence (with hold times in both directions).
        if self.effective == DanceState.IDLE:
            self._music_timer = self._music_timer + dt if activity >= t.music_on else 0.0
            if self._music_timer >= t.music_on_hold:
                self._music_timer = 0.0
                self.level = self.initial_level(drive)
                self._go(self.level)
            return self.state
        self._music_timer = self._music_timer + dt if activity < t.music_off else 0.0
        if self._music_timer >= t.music_off_hold:
            self._music_timer = 0.0
            self._pending = None
            self._go(DanceState.IDLE)
            return self.state

        if self.effective == DanceState.FLOURISH:
            if self.time_in_state >= t.flourish_max:
                self._go(self.level)
            return self.state

        if (
            surge
            and self.effective in (DanceState.GROOVE, DanceState.ENERGETIC)
            and self._since_flourish >= t.flourish_cooldown
        ):
            self._since_flourish = 0.0
            self._pending = None
            self._go(DanceState.FLOURISH)
            return self.state

        desired = self._desired_level(drive)
        if desired != self.level:
            if self._pending != desired:
                self._pending = desired
                self._pending_for = 0.0
            self._pending_for += dt
            if self._pending_for >= t.level_hold and self.time_in_state >= t.min_dwell:
                self._pending = None
                self._go(desired)
        else:
            self._pending = None
        return self.state
