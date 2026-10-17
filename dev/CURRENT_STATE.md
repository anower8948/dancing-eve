# Current state — read this first

_Last updated: 2026-10-17 (session 3: Windows/Linux compatibility work)._

**Session 3:** Ubuntu 24.04 verified in Docker (`tests/platform/run_linux_tests.sh`):
setup, 159 tests, real PulseAudio monitor capture, rendering, headless-EGL and software
fallbacks, PyInstaller build. Renderer fallback chain added; setup offers missing apt
packages; Windows long-path warning; CI workflow `.github/workflows/platforms.yml` for
Windows + Ubuntu — **green** (run 38988911454): run.bat setup, 159 tests, real WASAPI
loopback capture via VB-CABLE (119.9 BPM), software-rendered app 58 FPS, packaged .exe.
CI found two Windows bugs, both fixed: SoundCard/COM init order (capture was
"unavailable") and blank parasite buffers from the hidden-host-window renderer attempt.

## In one paragraph

First usable release on macOS. Launch with `run.command` (or `python3 setup/bootstrap.py`):
first-time setup creates `.venv`, installs exact pins with real progress, validates, and
starts the app. A procedurally modelled white robot (egg body, floating head, dark visor,
glowing blue eyes, paddle arms, chest light, soft shadow) floats in a transparent,
frameless, always-on-top Qt window. Real system audio is captured with ScreenCaptureKit,
analysed on a worker thread (bands, flux, onsets, tempo, phase-locked beats, silence,
surges) and drives a choreography engine (state machine + 27 movement primitives +
call-and-response phrases + crossfades + beat impulses) feeding a spring-based layered animation system.
Windows/Ubuntu code paths exist but have never been run.

## Environment used

macOS 27.0 (26A428), Apple M2 (8-core CPU, 10-core GPU), Python 3.12.13 (Homebrew,
`/opt/homebrew/opt/python@3.12`), Panda3D 1.10.16 (OpenGL 2.1 Metal), PySide6-Essentials
6.12.0, NumPy 2.5.4, PyObjC 12.2.2, SoundCard 0.4.6. Default `python3` on the machine is
3.14 (unsupported); the bootstrap picks 3.12 automatically.

## Working (verified on macOS)

* Setup: first run (18 s, warm pip cache), repeat run 0.9 s, per-package progress.
* Real capture: tone/beat/song via `afplay` captured; tempo locked at 100.1 BPM on a
  synthetic song; start/stop cycles release the stream (see docs/audio-capture.md).
* Rendering: transparent window over other apps (screen capture), MSAA 4×, Retina-aware.
* App: demo mode, live mode (GROOVE state reached from real audio), settings window with
  debug panel, single instance, clean shutdown, settings persistence.
* Performance: dancing 58 FPS, 3.6 ms/frame, 20 % of one core, ~240 MB RSS; idle 24 FPS ≈ 10 %; sleepy 15 FPS ≈ 9 %.
* Session 2: 14 new moves (incl. a second flourish), phrase planner, surprised/sleepy
  expressions, bolder happy eyes, overhead arm poses, wider 1:1 window, monotonic dance
  clock. Checked with rendered pose sheets and tests — not yet watched live with real songs.
* PyInstaller `dist/ProjectEVE.app` (157 MB): renders and captures when run from terminal.
* Quality: 159 tests pass; ruff + mypy clean.

## Incomplete / unverified

* Windows: GPU rendering, desktop behaviour (transparency, tray, drag, DPI) on a real PC.
* Ubuntu desktop: transparency, tray, always-on-top, PipeWire, real GPU (container only so far).
* macOS: permission-denied flow live; drag/click-through/tray menu by hand;
  double-clicking `run.command` in Finder and the `.app` in Finder.
* External model loading (hook only); GUI setup window; launch at login.

## Important files

* `setup/bootstrap.py`, `setup/setup_manager.py` — launcher logic.
* `src/eve/application.py` — composition root, frame loop, AppController.
* `src/eve/audio/analyzer.py`, `beat_detector.py`, `tempo_estimator.py` — analysis.
* `src/eve/audio/platforms/macos_capture.py` — ScreenCaptureKit backend.
* `src/eve/dance/dance_controller.py`, `movement_library.py`, `dance_state.py`.
* `src/eve/animation/animation_controller.py`, `spring_dynamics.py`.
* `src/eve/character/eve_character.py`, `character_geometry.py`; `src/eve/rendering/*`.

## Recent test results

`.venv/bin/python scripts/run_dev.py check` → ruff OK, format OK, mypy OK (75 files),
pytest **159 passed** (~15 s, includes real Qt+Panda3D start-up tests).

## Known bugs / rough edges

* Tempo octave errors on some patterns (docs/known-limitations.md #3).
* CPU ~20 % of a core while dancing from synchronous readback (idle ~10 %).
* New moves need live tuning with real music.
* The window is now square (aspect 1.0) and the default size 280 px; existing users keep
  their saved size, so the robot looks ~9 % smaller than before at the same size.

## Immediate next steps

See [NEXT_STEPS.md](NEXT_STEPS.md): test on Windows, test on Ubuntu, live permission
walkthrough on macOS, manual interaction pass, CPU reduction.

## How to resume

```bash
cd <project>
.venv/bin/python scripts/run_dev.py check          # everything should pass
.venv/bin/python scripts/run_dev.py --demo         # watch it dance without audio
PYTHONPATH=src .venv/bin/python -m eve --test-capture 10   # real capture (play music)
```
