"""Build Project EVE for Windows (must be run on Windows). See docs/packaging.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_app

if __name__ == "__main__":
    if not sys.platform.startswith("win32"):
        print("build_windows.py must be run on Windows (PyInstaller cannot cross-compile).")
        raise SystemExit(2)
    raise SystemExit(build_app.main())
