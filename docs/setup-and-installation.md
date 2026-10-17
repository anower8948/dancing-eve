# Setup and installation

## Launchers

| OS | Start EVE by | Notes |
|---|---|---|
| macOS | double-clicking **`run.command`** | Opens Terminal. If macOS says it "cannot be opened", right-click → **Open** → Open (or System Settings → Privacy & Security → *Open Anyway*). This happens for files downloaded as a zip; it is macOS protecting you, so EVE does not try to bypass it. |
| Windows | double-clicking **`run.bat`** | Opens a console window that shows setup progress and EVE's messages. |
| Ubuntu | `./run-ubuntu.sh`, or right-click → *Run as a Program* in Files | If started without a terminal it reopens itself in GNOME Terminal/Konsole/xterm. One-time: `chmod +x run-ubuntu.sh` if the executable bit was lost. `./run-ubuntu.sh --install-desktop-entry` adds "Project EVE" to the app menu. |

All launchers resolve paths relative to themselves (paths with spaces work, the folder can
be moved), find any Python ≥ 3.8 to run `setup/bootstrap.py`, keep the window open on
errors, and return the exit code.

## What the first launch does

`setup/bootstrap.py` (standard library only) shows a real progress display:

```
[ 20%] Creating virtual environment: done (.venv)
[ 42%] Installing dependencies: running (5 of 12 packages: SoundCard)
```
(in an interactive terminal it is a redrawn panel with a bar and ✓ marks).

1. **Detect OS** (macOS / Windows / Linux distro + session type).
2. **Check Python** — finds 3.12, 3.13 or 3.11 (`py -3.x` on Windows, Homebrew and
   python.org locations on macOS). If none exists it offers a safe install and asks first:
   `brew install python@3.12` (macOS, if Homebrew exists), `winget install --scope user`
   (Windows), `sudo apt-get install python3 python3-venv` (Ubuntu; explains why sudo is
   needed). Otherwise it prints exact manual instructions and stops.
3. **Check system requirements** — macOS ≥ 13 for native capture; on Linux the shared
   libraries Qt/Panda3D/SoundCard need (`libxcb-cursor0`, `libpulse0`, `libgl1`,
   `libegl1`, `libxkbcommon0`).
4. **Create `.venv`** inside the project (no admin rights, nothing global).
5. **Install dependencies** from `requirements.txt` (exact pins incl. transitive deps).
   Progress advances per package pip resolves.
6. **Validate** installed versions against the pins and import the key modules.
7. **Check audio support** (`python -m eve --diagnose-audio --json`; never prompts).
8. **Launch** `python -m eve` with `PYTHONPATH=src`.

Measured on the dev Mac: first run 18 s with a warm pip cache (expect a few minutes and
~150 MB of downloads on a fresh machine); the venv occupies ~0.8 GB (Qt and Panda3D are
large).

## Later launches

The venv is reused. A marker (`.venv/.eve-install.json`) stores a fingerprint of
`requirements.txt` + Python version + OS; if it matches and installed versions still
match the pins, installation is skipped (measured 0.9 s for all setup steps). Changing a
pin, upgrading Python or a damaged venv triggers a re-sync automatically.

`python3 setup/bootstrap.py --repair` forces a re-sync; `--no-launch` prepares only;
`--yes` answers install prompts; anything after `--` is passed to EVE
(e.g. `./run-ubuntu.sh -- --demo`).

## Failures and recovery

* **Network failure:** pip retries 3× internally, the setup retries twice more with
  backoff, then (in a terminal) asks "Retry now?". It then stops, names the failed step,
  explains the problem and keeps everything already downloaded/installed. Running the
  launcher again resumes. The marker is written only after validation succeeds.
* **Broken venv:** moved aside to `.venv.broken` (not deleted outright) and recreated.
* **Concurrent launches:** a lock file in `.eve-setup/` prevents two setups at once (stale
  locks from crashed runs are detected).
* **Logs:** `setup.log` in the log directory below (rotated at 1 MB).

After installation EVE needs no network access. No AI models are downloaded.

## Where things are stored

| | macOS | Windows | Linux |
|---|---|---|---|
| Settings | `~/Library/Application Support/ProjectEVE/settings.json` | `%APPDATA%\ProjectEVE\settings.json` | `~/.config/ProjectEVE/settings.json` |
| Logs (`eve.log`, `setup.log`) | `~/Library/Logs/ProjectEVE/` | `%LOCALAPPDATA%\ProjectEVE\Logs\` | `~/.local/state/ProjectEVE/log/` |
| Single-instance lock | next to settings | next to settings | next to settings |
| Virtual environment | `<project>/.venv` | same | same |

Set `EVE_HOME=/some/folder` to keep settings and logs in one folder (portable/testing).
Updating the project folder (git pull / new zip) never touches settings.

## Manual / developer install

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
PYTHONPATH=src .venv/bin/python -m eve --demo
.venv/bin/python scripts/run_dev.py check
```
