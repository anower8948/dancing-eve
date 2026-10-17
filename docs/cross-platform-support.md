# Cross-platform support matrix

Legend: **Verified** = run and observed on that OS · **Partial** = some aspects observed ·
**Planned** = implemented or designed but never run on that OS · **Unsupported**.

Only macOS 27.0 (Apple M2) was available during development. Nothing below is marked
verified for Windows or Ubuntu.

| Feature | macOS 13+ | Windows 10/11 | Ubuntu X11 / XWayland | Ubuntu native Wayland |
|---|---|---|---|---|
| Launcher + first-time setup | **Verified** (`bootstrap.py`; `run.command` itself not double-clicked in Finder) | Planned (`run.bat`) | Planned (`run-ubuntu.sh`) | Planned |
| Repeat launch reuses venv | **Verified** (0.9 s) | Planned | Planned | Planned |
| System-audio capture | **Verified** (ScreenCaptureKit) | Planned (WASAPI loopback) | Planned (Pulse/PipeWire monitor) | Planned (same) |
| Capture permission handling | Partial (granted path verified; denied path unit-tested only) | n/a (no prompt) | n/a | n/a |
| Virtual-device fallback | Planned (BlackHole) | — | — | — |
| Offscreen 3D rendering | **Verified** (GL 2.1 Metal, MSAA 4×) | Planned (WGL) | Planned (GLX) | Planned (needs XWayland) |
| Transparent window | **Verified** (screen capture) | Planned | Planned (needs compositor) | Planned |
| Always on top | **Verified** | Planned | Planned | Unsupported (we prefer XWayland) |
| Click-through | Planned (implemented, not exercised) | Planned | Planned | Unsupported |
| Drag to move | Planned (native `startSystemMove`, not exercised by hand) | Planned | Planned | Planned |
| Tray / menu-bar icon | Partial (created without errors; menu not clicked) | Planned | Planned (GNOME needs AppIndicator) | Planned |
| Settings window + debug panel | **Verified** (rendered to image) | Planned | Planned | Planned |
| Settings storage paths | **Verified** (macOS); unit-tested for all | Unit-tested | Unit-tested | Unit-tested |
| Single instance | **Verified** (integration test) | Planned | Planned | Planned |
| PyInstaller build | see [packaging.md](packaging.md) | Planned | Planned | Planned |

## Platform notes

* **macOS:** Screen & System Audio Recording permission for the launching app. The
  companion is a `Qt.Tool` window with `WA_MacAlwaysShowToolWindow` so it stays visible
  when other apps are active. The app also shows a Dock icon (an easy way to quit).
* **Windows:** tool window = no taskbar entry; tray icon is the control point. Clicks on
  fully transparent pixels pass through layered windows.
* **Linux:** on a Wayland session EVE sets `QT_QPA_PLATFORM=xcb` when XWayland is available
  (always-on-top and positioning are not available to normal Wayland clients; Panda3D's
  GL pipe also needs an X display). Override by setting `QT_QPA_PLATFORM` yourself.
  Qt 6.5+ needs `libxcb-cursor0`; the setup checks for it.
