"""Silence detection with level hysteresis and hold times."""

from __future__ import annotations


class SilenceDetector:
    """``enter_db``/``exit_db`` form a hysteresis band so a quiet passage does not flicker.

    Silence is declared after the level stays below ``enter_db`` for ``enter_hold`` seconds,
    and cleared once it stays above ``exit_db`` for ``exit_hold`` seconds.
    """

    def __init__(
        self,
        enter_db: float = -60.0,
        exit_db: float = -52.0,
        enter_hold: float = 0.8,
        exit_hold: float = 0.08,
    ) -> None:
        if exit_db < enter_db:
            raise ValueError("exit_db must be >= enter_db")
        self.enter_db = enter_db
        self.exit_db = exit_db
        self.enter_hold = enter_hold
        self.exit_hold = exit_hold
        self.is_silent = True
        self._timer = 0.0

    def update(self, level_db: float, dt: float) -> bool:
        if self.is_silent:
            if level_db > self.exit_db:
                self._timer += dt
                if self._timer >= self.exit_hold:
                    self.is_silent = False
                    self._timer = 0.0
            else:
                self._timer = 0.0
        else:
            if level_db < self.enter_db:
                self._timer += dt
                if self._timer >= self.enter_hold:
                    self.is_silent = True
                    self._timer = 0.0
            else:
                self._timer = 0.0
        return self.is_silent

    def reset(self) -> None:
        self.is_silent = True
        self._timer = 0.0
