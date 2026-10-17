# Cross-platform support matrix

Legend: **Verified** = run and observed · **Verified (container)** = run on Ubuntu 24.04
arm64 in Docker with a virtual display (Xvfb), software OpenGL (Mesa llvmpipe) and a
PulseAudio server (`tests/platform/run_linux_tests.sh`) — real Ubuntu userland, but no
real desktop, GPU, compositor or speakers · **CI** = covered by
`.github/workflows/platforms.yml` (results only once it has run on GitHub) ·
**Planned** = implemented, never run on that OS · **Unsupported**.

Development machine: macOS 27.0 (Apple M2). No Windows machine was available.

| Feature | macOS 13+ | Windows 10/11 | Ubuntu X11 / XWayland | Ubuntu native Wayland |
|---|---|---|---|---|
| Launcher + first-time setup | **Verified** (`run.command` from a terminal) | CI (`run.bat`) | **Verified (container)** (`run-ubuntu.sh`, 26 s) | same as X11 |
| Repeat launch reuses venv | **Verified** (0.9 s) | CI | **Verified (container)** | same |
| Full test suite (159 tests) | **Verified** | CI | **Verified (container)** incl. Qt + 3D tests | — |
| System-audio capture | **Verified** (ScreenCaptureKit) | Planned (WASAPI loopback; CI has no audio device) | **Verified (container)**: PulseAudio monitor, 119.9 BPM on a 120 BPM beat | same (needs `pipewire-pulse`) |
| Capture permission handling | Partial (granted path verified; denied path unit-tested) | n/a (no prompt) | n/a | n/a |
| Virtual-device fallback | Planned (BlackHole) | — | — | — |
| 3D rendering, full shading | **Verified** (GL 2.1 Metal, MSAA 4×) | Planned (WGL; CI machine has no GPU) | **Verified (container)** (Mesa llvmpipe GL 4.5) | Planned |
| Headless EGL fallback (no X display) | — | — | **Verified (container)** | intended for pure Wayland |
| Software renderer fallback | **Verified** (`EVE_RENDERER=software`) | CI (expected on GPU-less runner) | **Verified (container)** | Planned |
| Transparent window | **Verified** (screen capture) | Planned | Planned (needs compositor) | Planned |
| Always on top | **Verified** | Planned | Planned | Unsupported (we prefer XWayland) |
| Click-through | Planned (implemented, not exercised) | Planned | Planned | Unsupported |
| Drag to move | Planned (not exercised by hand) | Planned | Planned | Planned |
| Tray / menu-bar icon | Partial (created; menu not clicked) | Planned | Planned (GNOME needs AppIndicator) | Planned |
| Settings window + debug panel | **Verified** (rendered to image) | Planned | Planned | Planned |
| Settings storage paths | **Verified**; unit-tested for all | Unit-tested | **Verified (container)** | same |
| Single instance | **Verified** | CI | **Verified (container)** (integration test) | same |
| PyInstaller build runs | **Verified** (`ProjectEVE.app`, 157 MB) | CI | **Verified (container)** (233 MB folder; GL and software renderer) | same |

## What still needs a real machine

* **Windows:** everything until the CI workflow has run; after that, real WASAPI capture
  with speakers/headphones, GPU rendering, transparency, tray, drag and click-through.
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
