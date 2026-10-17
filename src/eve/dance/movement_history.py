"""Recent-movement memory used to avoid repetitive choreography."""

from __future__ import annotations

from collections import deque


class MovementHistory:
    def __init__(self, size: int = 12) -> None:
        self._recent: deque[str] = deque(maxlen=size)
        self._last_used: dict[str, float] = {}

    def record(self, name: str, now: float) -> None:
        self._recent.append(name)
        self._last_used[name] = now

    @property
    def last(self) -> str | None:
        return self._recent[-1] if self._recent else None

    def count_recent(self, name: str, window: int = 4) -> int:
        recent = list(self._recent)[-window:]
        return recent.count(name)

    def seconds_since(self, name: str, now: float) -> float:
        used = self._last_used.get(name)
        return float("inf") if used is None else now - used

    def recent(self) -> list[str]:
        return list(self._recent)
