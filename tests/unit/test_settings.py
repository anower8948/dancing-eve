"""Settings validation, persistence, migrations and corruption recovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eve.config import SETTINGS_VERSION, Settings, validate
from eve.storage.migrations import MigrationError, migrate
from eve.storage.settings_store import SettingsStore


def test_defaults_are_valid() -> None:
    settings, problems = validate(Settings().to_dict())
    assert problems == []
    assert settings == Settings()


def test_validation_clamps_and_fixes_types() -> None:
    settings, problems = validate(
        {
            "sensitivity": 99,
            "dance_intensity": -3,
            "character_size": "big",
            "always_on_top": "yes",
            "window_x": 12.7,
            "target_fps": float("nan"),
            "bogus": 1,
        }
    )
    assert settings.sensitivity == 3.0
    assert settings.dance_intensity == 0.0
    assert settings.character_size == Settings().character_size
    assert settings.always_on_top is True  # invalid type -> default
    assert settings.window_x == 12
    assert settings.target_fps == Settings().target_fps
    assert any("bogus" in p for p in problems)


def test_effective_fps_power_saving() -> None:
    assert Settings(power_saving=True, target_fps=60).effective_fps == 30
    assert Settings(power_saving=False, target_fps=60).effective_fps == 60


def test_store_roundtrip_and_atomic_save(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    assert store.load() == Settings()
    settings = Settings(sensitivity=1.7, character_size=300, audio_source_id="sck:system")
    assert store.save(settings)
    assert SettingsStore(tmp_path / "settings.json").load() == settings
    assert not list(tmp_path.glob(".settings-*"))  # no temp files left behind


def test_corrupted_file_is_preserved_and_defaults_used(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    store = SettingsStore(path)
    assert store.load() == Settings()
    assert store.notices
    backups = list(tmp_path.glob("settings.corrupt-*.json"))
    assert len(backups) == 1 and backups[0].read_text() == "{not json"


def test_newer_version_is_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"version": SETTINGS_VERSION + 5, "sensitivity": 2.0}), encoding="utf-8")
    store = SettingsStore(path)
    assert store.load() == Settings()
    assert store.read_only
    assert store.save(Settings()) is False
    assert json.loads(path.read_text())["version"] == SETTINGS_VERSION + 5


def test_migration_from_unversioned_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"volume_sensitivity": 2.0, "size": 320}), encoding="utf-8")
    settings = SettingsStore(path).load()
    assert settings.sensitivity == 2.0 and settings.character_size == 320
    saved = json.loads(path.read_text())
    assert saved["version"] == SETTINGS_VERSION and "volume_sensitivity" not in saved


def test_migrate_rejects_invalid_versions() -> None:
    with pytest.raises(MigrationError):
        migrate({"version": -1})
    with pytest.raises(MigrationError):
        migrate({"version": "1"})
    data, applied = migrate({"version": SETTINGS_VERSION})
    assert applied == []


def test_reset_keeps_backup(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.save(Settings(sensitivity=2.5))
    assert store.reset() == Settings()
    assert list(tmp_path.glob("settings.before-reset-*.json"))
    assert SettingsStore(path).load() == Settings()


def test_dance_style_choices_match_the_library() -> None:
    from eve.config import CHOICES
    from eve.dance.movement_library import DANCE_STYLES

    assert set(CHOICES["dance_style"]) == set(DANCE_STYLES)
    assert validate({"dance_style": "dreamers"})[0].dance_style == "dreamers"
    assert validate({"dance_style": "salsa"})[0].dance_style == "mixed"
