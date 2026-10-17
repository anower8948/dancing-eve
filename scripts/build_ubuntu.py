"""Build Project EVE for Ubuntu Linux (must be run on Ubuntu Linux). See docs/packaging.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_app

if __name__ == "__main__":
    if not sys.platform.startswith("linux"):
        print("build_ubuntu.py must be run on Ubuntu Linux (PyInstaller cannot cross-compile).")
        raise SystemExit(2)
    raise SystemExit(build_app.main())
