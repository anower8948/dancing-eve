# Troubleshooting

Logs: see [setup-and-installation.md](setup-and-installation.md#where-things-are-stored)
(Settings → Advanced → *Open log folder*). Add `--debug` for verbose logs.

| Symptom | Cause / fix |
|---|---|
| macOS: "run.command cannot be opened because it is from an unidentified developer" | Downloaded-zip quarantine. Right-click → Open → Open, or System Settings → Privacy & Security → Open Anyway. |
| macOS: status "Permission denied" | Allow the launching app (Terminal, or ProjectEVE.app) in System Settings → Privacy & Security → **Screen & System Audio Recording**, **quit and reopen** that app, press Retry. |
| macOS: "Listening — nothing is playing" while music plays | The music app may be using exclusive/hardware output, or plays through AirPlay from another device. Check with `--test-capture 10`. |
| Packaged macOS app keeps losing the permission | Ad-hoc signed builds change identity on every rebuild; macOS forgets the grant. Use a stable Developer ID signature. |
| Windows: "No capturable output device found" | No active output endpoint; plug in/enable speakers/headphones. Exclusive-mode apps cannot be captured. |
| Ubuntu: no sources / "SoundCard library unavailable" | Install `libpulse0`; make sure PulseAudio or `pipewire-pulse` runs (`pactl info`). Pure-ALSA systems are unsupported. |
| Ubuntu: Qt error "Could not load the Qt platform plugin xcb" | `sudo apt install libxcb-cursor0` |
| Ubuntu: black box instead of transparency | No compositing window manager. Use GNOME/KDE or enable compositing. |
| Ubuntu: no tray icon | GNOME needs the AppIndicator extension (enabled on stock Ubuntu). Without a tray, EVE disables click-through and hiding so it can never get stuck. |
| "The 3D renderer could not start" | OpenGL 2.1+ driver required. On VMs/remote desktops, enable 3D acceleration. |
| Robot does not react although status is Listening | Raise *Audio sensitivity*; check the debug panel (Music activity, Tempo). Very quiet/ambient music stays in CALM by design. |
| Robot follows the beat oddly (double/half speed) | Tempo octave ambiguity (e.g. slow songs with busy hi-hats). Dancing still stays on the grid; better tracking is on the roadmap. |
| "Project EVE is already running" | Another instance holds the lock. Use its tray icon. A stale lock from a crash is cleared automatically. |
| Click-through on and I can't click the robot | Use the tray / menu-bar icon → uncheck *Click-through*, or open Settings from the tray. |
| Setup fails downloading packages | Check the connection/proxy and run the launcher again; finished downloads are kept. `python3 setup/bootstrap.py --repair` re-syncs everything. |
| Setup says no supported Python | Install Python 3.12 (python.org or the offered package-manager command) and relaunch. |
| Reset everything | Settings → *Reset preferences…* (old file kept as backup), or `--reset-settings`. Deleting `.venv` forces a fresh install. |
