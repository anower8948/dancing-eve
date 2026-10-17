"""Logging: bounded rotating file + console. Never logs raw audio."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

LOG_FILE_BYTES = 1_000_000
LOG_BACKUPS = 3


def configure_logging(log_dir: Path, debug: bool = False) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "eve.log"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=LOG_FILE_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(logging.DEBUG if debug else logging.WARNING)
    root.addHandler(console)
    return path
