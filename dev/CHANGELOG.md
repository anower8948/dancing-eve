# Changelog

## 0.1.0 — 2026-10-17 (first release, macOS verified)

### Added
- One-click launchers (`run.command`, `run.bat`, `run-ubuntu.sh`) with stdlib-only
  first-time setup: Python discovery/optional install, project venv, exact pins,
  genuine progress, validation, audio check, network-failure recovery, setup lock.
- System-audio capture: ScreenCaptureKit (macOS, verified), WASAPI loopback (Windows),
  PulseAudio/PipeWire monitors (Linux), virtual loopback devices (macOS fallback);
  honest capture statuses with retries; no microphone fallback.
- Real-time analysis: bands, spectral flux, onsets, tempo with conservative confidence,
  phase-locked beats, silence, surges; volume-independent normalisation.
- Procedural 3D robot with custom GLSL shading, rendered offscreen by Panda3D into a
  transparent always-on-top Qt window.
- Layered spring animation (idle life, secondary motion, accents) and a music-aware
  choreography engine (6 states, 13 movements, history/cooldowns, crossfades).
- Tray/menu-bar control, settings window, debug panel, demo mode, diagnostics,
  smoke-test performance report, single instance, versioned settings with migrations.
- 138 automated tests; docs; PyInstaller build scripts (macOS build verified).
