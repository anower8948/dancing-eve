"""Development helper: run the app or the quality checks with the project venv.

.venv/bin/python scripts/run_dev.py              # run EVE (extra args passed through)
.venv/bin/python scripts/run_dev.py --demo       # dance to the built-in virtual song
.venv/bin/python scripts/run_dev.py check        # ruff + mypy + pytest
.venv/bin/python scripts/run_dev.py --install-dev
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd), flush=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main(argv: list[str]) -> int:
    py = sys.executable
    if argv[:1] == ["--install-dev"]:
        return run([py, "-m", "pip", "install", "-r", "requirements-dev.txt"])
    if argv[:1] == ["check"]:
        for cmd in (
            [py, "-m", "ruff", "check", "."],
            [py, "-m", "ruff", "format", "--check", "."],
            [py, "-m", "mypy"],
            [py, "-m", "pytest", "-o", "addopts=", "-q"],
        ):
            code = run(cmd)
            if code:
                return code
        return 0
    return run([py, "-m", "eve", *argv])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
