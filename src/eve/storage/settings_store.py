"""JSON settings persistence: atomic writes, migrations, corruption recovery.

* Writes go to a temp file that is atomically renamed over the real one.
* A file that cannot be parsed is moved aside as ``settings.corrupt-<timestamp>.json``
  (never deleted) and defaults are used.
* A file from a *newer* app version is left untouched and defaults are used in memory,
  so downgrading never destroys the user's newer settings.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path

from eve.config import Settings, validate
from eve.storage.migrations import MigrationError, migrate

log = logging.getLogger(__name__)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.read_only = False  # set when the file belongs to a newer app version
        self.notices: list[str] = []  # user-facing notes from the last load

    def load(self) -> Settings:
        self.notices = []
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings file is not a JSON object")
        except (OSError, ValueError) as exc:
            backup = self._quarantine()
            self.notices.append(
                f"Settings file was unreadable ({exc}); defaults restored. "
                f"Old file kept as {backup.name if backup else 'n/a'}."
            )
            log.warning(self.notices[-1])
            return Settings()
        try:
            raw, applied = migrate(raw)
        except MigrationError as exc:
            self.read_only = True
            self.notices.append(f"{exc}; using defaults without overwriting the file.")
            log.warning(self.notices[-1])
            return Settings()
        settings, problems = validate(raw)
        if applied:
            log.info("migrated settings from version(s) %s", applied)
        for problem in problems:
            log.info("settings fix: %s", problem)
        if applied or problems:
            self.save(settings)
        return settings

    def save(self, settings: Settings) -> bool:
        if self.read_only:
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=str(self.path.parent))
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(settings.to_dict(), handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
            return True
        except OSError:
            log.exception("could not save settings to %s", self.path)
            return False

    def reset(self) -> Settings:
        """Restore defaults (the previous file is kept as a backup)."""
        if self.path.exists():
            backup = self.path.with_name(f"settings.before-reset-{time.strftime('%Y%m%d-%H%M%S')}.json")
            try:
                os.replace(self.path, backup)
            except OSError:
                log.exception("could not back up settings before reset")
        self.read_only = False
        settings = Settings()
        self.save(settings)
        return settings

    def _quarantine(self) -> Path | None:
        backup = self.path.with_name(f"settings.corrupt-{time.strftime('%Y%m%d-%H%M%S')}.json")
        try:
            os.replace(self.path, backup)
            return backup
        except OSError:
            return None
