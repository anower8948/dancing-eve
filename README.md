# Project EVE

A small, original floating robot that lives on your desktop and **dances to whatever
your computer is playing** — Spotify, YouTube in a browser, a game. It listens to the
real system audio output (never the microphone), analyses rhythm locally, and moves with
springy, layered, varied choreography: calm sways for quiet songs, bounces and spins for
energetic ones, a celebratory flourish when the music drops, and a gentle idle (floating,
breathing, blinking, glancing) when the music stops.

Free, local, no accounts, no cloud. Python + PySide6 + Panda3D + NumPy.

> Inspired by the general aesthetic of cute futuristic floating robots. The design,
> geometry and code are original; the project is not affiliated with any film studio.

## Quick start

| OS | Do this |
|---|---|
| **macOS 13+** | Double-click **`run.command`**. On first listen, allow *Terminal* in System Settings → Privacy & Security → **Screen & System Audio Recording**, reopen Terminal, press Retry. |
| **Windows 10/11** | Double-click **`run.bat`**. |
| **Ubuntu** | Run **`./run-ubuntu.sh`** (or right-click → *Run as a Program*). |

The first launch creates a private `.venv`, installs pinned dependencies with a progress
display, checks audio support and starts EVE. Later launches start in about a second.
Details: [docs/setup-and-installation.md](docs/setup-and-installation.md).

## Using EVE

* **Drag** the robot to move it · **click** to poke it · **double-click** for Settings ·
  **right-click** for the menu · **Ctrl/⌘ + scroll** to resize · **⌘Q/Ctrl+Q** to quit.
* The **tray / menu-bar icon** controls listening, visibility, always-on-top and
  click-through, and always offers *Quit*.
* A small **dot** on the robot shows listening status (green = hearing music).
* Settings: sensitivity, dance intensity, reduced motion, size, always on top,
  click-through, power saving, shadow, debug panel (live analysis values and a
  "Play move" tester), reset preferences.
* `--demo` dances to a built-in virtual song without capturing audio.

## Status (2026-10-17)

| | |
|---|---|
| macOS (Apple Silicon) | **Working and verified** — real system-audio capture, rendering, transparency, setup, packaging. |
| Windows / Ubuntu | **Implemented, not yet tested on real machines.** |

157 automated tests pass; ruff and mypy are clean. See
[docs/cross-platform-support.md](docs/cross-platform-support.md) and
[docs/known-limitations.md](docs/known-limitations.md).

## Command line

```bash
PYTHONPATH=src .venv/bin/python -m eve [--demo] [--no-audio] [--debug] [--size 300] [--fps 30]
PYTHONPATH=src .venv/bin/python -m eve --diagnose-audio       # which capture backends work here
PYTHONPATH=src .venv/bin/python -m eve --test-capture 10      # capture real audio for 10 s
PYTHONPATH=src .venv/bin/python -m eve --smoke-test 20        # run 20 s, print performance
.venv/bin/python scripts/run_dev.py check                     # lint + types + tests
.venv/bin/python scripts/build_macos.py                       # standalone app (per OS)
```

## Documentation

[docs/README.md](docs/README.md) indexes everything: architecture, decisions, audio
capture, animation, rendering, platform matrix, setup, packaging, testing,
troubleshooting, privacy, limitations, roadmap. Development state for the next session:
[dev/CURRENT_STATE.md](dev/CURRENT_STATE.md).

## License

MIT — see [LICENSE](LICENSE).
# dancing-eve
