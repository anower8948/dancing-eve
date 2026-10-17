"""Ordered, failure-tolerant shutdown.

Resources register a cleanup callback as they start; shutdown runs them in reverse order
and continues even if one fails, so a renderer error can never keep the audio device open.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


class ShutdownSequence:
    def __init__(self) -> None:
        self._steps: list[tuple[str, Callable[[], object]]] = []
        self.completed = False

    def add(self, name: str, callback: Callable[[], object]) -> None:
        self._steps.append((name, callback))

    def run(self) -> list[tuple[str, bool]]:
        """Run every cleanup once, last registered first. Returns (name, succeeded)."""
        if self.completed:
            return []
        results = []
        for name, callback in reversed(self._steps):
            try:
                callback()
                results.append((name, True))
            except Exception:
                log.exception("cleanup step %r failed", name)
                results.append((name, False))
        self.completed = True
        return results
