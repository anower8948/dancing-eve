# TODO

## P1
- [ ] Windows real-hardware test (capture, launcher, window, tray, build)
- [ ] Ubuntu real-hardware test (PipeWire monitor, XWayland, tray, build)
- [ ] macOS permission-denied live test
- [ ] Manual interaction pass (drag, click-through, tray, multi-monitor DPI)
- [ ] Tune choreography against real songs

## P2
- [ ] Async GPU readback (idle already lowered to ≈10 %)
- [ ] Downbeat / bar tracking; tempo octave resolution
- [ ] GUI setup window
- [ ] Hash-pinned per-OS lock files
- [ ] Developer ID signing + notarisation; Windows installer; AppImage
- [ ] Live-tune the session-2 moves with real songs

## P3
- [ ] External GLB/VRM characters via the joint-name hook
- [ ] User-defined movement sequences (JSON)
- [ ] Optional, explicit microphone mode
- [ ] Launch at login; localisation

## Done (session 2)
- [x] 14 new moves (27 total), second flourish (star_burst)
- [x] Call-and-response phrase planner
- [x] Surprised and sleepy expressions, bolder happy eyes
- [x] Overhead arm poses via spread; square window; tighter drift limit
- [x] Monotonic dance clock (bad phase input can't freeze moves)
- [x] Idle CPU ≈19 % → ≈10 % (single-pass paint, power save with debug on, 15 FPS sleepy)

## Done (session 1)
- [x] Environment inspection, capture & renderer feasibility probes
- [x] Setup system + three launchers + progress + recovery
- [x] Audio capture interface, manager, SCK/WASAPI/Pulse/virtual backends
- [x] Streaming analysis (bands, flux, onsets, tempo, beats, silence, surge)
- [x] Procedural robot, shaders, offscreen renderer
- [x] Springs, idle, secondary motion, 13 movements, state machine, transitions
- [x] Qt companion window, tray, settings, debug panel
- [x] 138 tests, ruff, mypy; macOS PyInstaller build
- [x] Documentation set and dev state files
