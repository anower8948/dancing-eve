# Cross-platform support matrix

Legend: **Verified** = run and observed · **Verified (container)** = run on Ubuntu 24.04
arm64 in Docker with a virtual display (Xvfb), software OpenGL (Mesa llvmpipe) and a
PulseAudio server (`tests/platform/run_linux_tests.sh`) — real Ubuntu userland, but no
real desktop, GPU, compositor or speakers · **Verified (CI)** = passed on GitHub Actions'
`windows-latest` (Windows Server, x64, no GPU, VB-CABLE virtual sound card) or
`ubuntu-24.04` (x64, Xvfb, Mesa, PulseAudio null sink) in `.github/workflows/platforms.yml`
(run 38988911454, 2026-10-17) · **Planned** = implemented, never run on that OS ·
**Unsupported**.

Development machine: macOS 27.0 (Apple M2). No physical Windows PC or Ubuntu desktop
was available; Windows evidence comes from CI.

| Feature | macOS 13+ | Windows 10/11 | Ubuntu X11 / XWayland | Ubuntu native Wayland |
|---|---|---|---|---|
| Launcher + first-time setup | **Verified** (`run.command` from a terminal) | **Verified (CI)** (`run.bat`, Python 3.12.10) | **Verified (container + CI)** (`run-ubuntu.sh`) | same as X11 |
| Repeat launch reuses venv | **Verified** (0.9 s) | **Verified (CI)** | **Verified (container + CI)** | same |
| Full test suite (159 tests) | **Verified** | **Verified (CI)** incl. Qt + 3D tests | **Verified (container + CI)** incl. Qt + 3D tests | — |
| System-audio capture | **Verified** (ScreenCaptureKit) | **Verified (CI)**: WASAPI loopback of a virtual cable, 661 k samples, 119.9 BPM on a 120 BPM beat | **Verified (container + CI)**: PulseAudio monitor, 119.9 BPM | same (needs `pipewire-pulse`) |
| Capture permission handling | Partial (granted path verified; denied path unit-tested) | n/a (no prompt) | n/a | n/a |
| Virtual-device fallback | Planned (BlackHole) | — | — | — |
| 3D rendering, full shading | **Verified** (GL 2.1 Metal, MSAA 4×) | Planned (needs a PC with a GPU; CI has none) | **Verified (container + CI)** (Mesa llvmpipe GL 4.5) | Planned |
| Headless EGL fallback (no X display) | — | — | **Verified (container)** | intended for pure Wayland |
| Software renderer fallback | **Verified** (`EVE_RENDERER=software`) | **Verified (CI)**: used automatically, 58 FPS | **Verified (container)** | Planned |
| Transparent window | **Verified** (screen capture) | Planned | Planned (needs compositor) | Planned |
| Always on top | **Verified** | Planned | Planned | Unsupported (we prefer XWayland) |
| Click-through | Planned (implemented, not exercised) | Planned | Planned | Unsupported |
| Drag to move | Planned (not exercised by hand) | Planned | Planned | Planned |
| Tray / menu-bar icon | Partial (created; menu not clicked) | Planned | Planned (GNOME needs AppIndicator) | Planned |
| Settings window + debug panel | **Verified** (rendered to image) | Planned | Planned | Planned |
| Settings storage paths | **Verified**; unit-tested for all | Unit-tested | **Verified (container)** | same |
| Single instance | **Verified** | **Verified (CI)** | **Verified (container + CI)** | same |
| PyInstaller build runs | **Verified** (`ProjectEVE.app`, 157 MB) | **Verified (CI)** (`ProjectEVE.exe`, 193 MB folder, 58 FPS) | **Verified (container + CI)** (233 MB folder) | same |

## What still needs a real machine

* **Windows:** GPU OpenGL rendering (CI has no GPU, so the full-quality look and the
  hidden-host-window path are unverified there), capture from real speakers/headphones,
  transparency, tray, drag, click-through, high-DPI scaling, double-clicking `run.bat` in
  Explorer, and Windows 10 (CI is Windows Server 2025).
* **Ubuntu desktop:** transparency with a compositor, always-on-top/tray under GNOME,
  PipeWire (Ubuntu's default) instead of plain PulseAudio, a real GPU, launching
  `run-ubuntu.sh` from the Files app, native Wayland sessions.

## Platform notes

* **macOS:** Screen & System Audio Recording permission for the launching app. The
  companion is a `Qt.Tool` window with `WA_MacAlwaysShowToolWindow` so it stays visible
  when other apps are active. The app also shows a Dock icon (an easy way to quit).
* **Windows:** tool window = no taskbar entry; tray icon is the control point. Clicks on
  fully transparent pixels pass through layered windows. The setup warns when a deep
  project folder may exceed the 260-character path limit. Remote Desktop sessions often
  only offer OpenGL 1.1 — EVE then uses simplified shading.
* **Linux:** on a Wayland session EVE sets `QT_QPA_PLATFORM=xcb` when XWayland is available
  (always-on-top and positioning are not available to normal Wayland clients). Without
  any X display the renderer falls back to headless EGL. Qt 6.5+ needs `libxcb-cursor0`
  and a few other X11 libraries; the setup detects missing ones and offers
  `sudo apt-get install` (asking first). Packaging needs `libpython3.12`.
* **Renderer fallback chain (all OSes):** GPU OpenGL → (Linux) headless EGL → built-in
  software rasteriser. Without GLSL (old GL, software) the robot uses simplified shading
  without glows or the soft shadow. `EVE_RENDERER=software` forces the last step.
