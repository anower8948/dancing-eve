"""Genuine, step-based setup progress reporting.

Progress is computed only from work that has actually finished: each step has a weight,
and a step contributes its full weight only after it reports success. A running step may
report a fraction of its own work (e.g. "12 of 20 packages collected").
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, TextIO

PENDING = "pending"
RUNNING = "running"
DONE = "done"
SKIPPED = "skipped"
FAILED = "failed"


@dataclass
class SetupStep:
    key: str
    title: str
    weight: float = 1.0
    state: str = PENDING
    fraction: float = 0.0
    detail: str = ""


class ProgressReporter:
    """Tracks setup steps and notifies a renderer on every change."""

    def __init__(self, steps: List[SetupStep], renderer: Optional[Callable[["ProgressReporter"], None]] = None):
        if not steps:
            raise ValueError("at least one step is required")
        self.steps = steps
        self._renderer = renderer
        self._by_key = {step.key: step for step in steps}
        self.current: Optional[SetupStep] = None

    # -- state changes -------------------------------------------------------------------
    def start(self, key: str, detail: str = "") -> None:
        step = self._by_key[key]
        step.state = RUNNING
        step.fraction = 0.0
        step.detail = detail
        self.current = step
        self._render()

    def update(self, key: str, fraction: float, detail: Optional[str] = None) -> None:
        step = self._by_key[key]
        # Never move backwards: a fake "jumpy" bar would be misleading.
        step.fraction = max(step.fraction, min(1.0, max(0.0, fraction)))
        if detail is not None:
            step.detail = detail
        self._render()

    def complete(self, key: str, detail: str = "") -> None:
        step = self._by_key[key]
        step.state = DONE
        step.fraction = 1.0
        if detail:
            step.detail = detail
        self._render()

    def skip(self, key: str, detail: str = "") -> None:
        step = self._by_key[key]
        step.state = SKIPPED
        step.fraction = 1.0
        step.detail = detail
        self._render()

    def fail(self, key: str, detail: str) -> None:
        step = self._by_key[key]
        step.state = FAILED
        step.detail = detail
        self._render()

    # -- queries -------------------------------------------------------------------------
    @property
    def percent(self) -> int:
        total = sum(step.weight for step in self.steps)
        done = 0.0
        for step in self.steps:
            if step.state in (DONE, SKIPPED):
                done += step.weight
            elif step.state == RUNNING:
                done += step.weight * step.fraction
        # 100% only when every step really finished.
        value = int(100.0 * done / total)
        if value >= 100 and not all(s.state in (DONE, SKIPPED) for s in self.steps):
            value = 99
        return value

    @property
    def failed(self) -> bool:
        return any(step.state == FAILED for step in self.steps)

    def _render(self) -> None:
        if self._renderer is not None:
            self._renderer(self)


def _supports_unicode(stream: TextIO) -> bool:
    encoding = (getattr(stream, "encoding", "") or "").lower()
    return "utf" in encoding


class TerminalRenderer:
    """Draws the progress panel in a terminal; falls back to plain log lines."""

    def __init__(self, stream: Optional[TextIO] = None, title: str = "PROJECT EVE — FIRST-TIME SETUP"):
        self.stream = stream or sys.stdout
        self.title = title
        self.interactive = bool(getattr(self.stream, "isatty", lambda: False)()) and os.environ.get("TERM") != "dumb"
        self.unicode = _supports_unicode(self.stream)
        self._last_plain = ""
        self._last_draw = 0.0
        self._lines_drawn = 0
        if self.interactive and sys.platform.startswith("win"):
            os.system("")  # enables ANSI escape processing on Windows 10+ consoles

    def __call__(self, reporter: ProgressReporter) -> None:
        if self.interactive:
            now = time.monotonic()
            # Rate-limit redraws while pip streams output, but always draw state changes.
            current = reporter.current
            if current is not None and current.state == RUNNING and now - self._last_draw < 0.1:
                return
            self._last_draw = now
            self._draw_panel(reporter)
        else:
            self._draw_plain(reporter)

    def _glyphs(self):
        if self.unicode:
            return "█", "░", "✓", "✗", "»", "–"
        return "#", ".", "x", "!", ">", "-"

    def _draw_panel(self, reporter: ProgressReporter) -> None:
        full, empty, ok, bad, run, skip = self._glyphs()
        width = 30
        filled = int(width * reporter.percent / 100)
        lines = [
            self.title if self.unicode else "PROJECT EVE - FIRST-TIME SETUP",
            "[{}{}] {:3d}%".format(full * filled, empty * (width - filled), reporter.percent),
        ]
        current = reporter.current
        if current is not None:
            task = current.title
            if current.detail:
                task += " — " + current.detail if self.unicode else " - " + current.detail
            lines.append("Current task: " + task[:100])
        lines.append("")
        for step in reporter.steps:
            mark = {DONE: ok, FAILED: bad, RUNNING: run, SKIPPED: skip}.get(step.state, " ")
            suffix = ""
            if step.state == SKIPPED and step.detail:
                suffix = " ({})".format(step.detail[:60])
            lines.append(" [{}] {}{}".format(mark, step.title, suffix))
        out = self.stream
        if self._lines_drawn:
            out.write("\x1b[{}F".format(self._lines_drawn))  # move cursor up
        for line in lines:
            out.write("\x1b[2K" + line + "\n")
        out.flush()
        self._lines_drawn = len(lines)

    def _draw_plain(self, reporter: ProgressReporter) -> None:
        current = reporter.current
        if current is None:
            return
        line = "[{:3d}%] {}: {}".format(reporter.percent, current.title, current.state)
        if current.detail:
            line += " ({})".format(current.detail)
        if line != self._last_plain:
            self.stream.write(line + "\n")
            self.stream.flush()
            self._last_plain = line

    def message(self, text: str) -> None:
        """Print a message below the panel (the panel is redrawn underneath next time)."""
        self.stream.write(text + "\n")
        self.stream.flush()
        self._lines_drawn = 0
