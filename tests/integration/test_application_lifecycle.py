"""Start the real application (Qt + Panda3D offscreen) in demo mode, then shut down.

Needs a display and OpenGL (marked ``gui``/``render``). Uses a temporary EVE_HOME so the
user's real settings are never touched.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from eve.core.lifecycle import ShutdownSequence

ROOT = Path(__file__).resolve().parents[2]


def test_shutdown_sequence_runs_in_reverse_and_tolerates_failures() -> None:
    calls: list[str] = []
    seq = ShutdownSequence()
    seq.add("audio", lambda: calls.append("audio"))
    seq.add("broken", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    seq.add("renderer", lambda: calls.append("renderer"))
    results = seq.run()
    assert calls == ["renderer", "audio"]
    assert ("broken", False) in results
    assert seq.run() == []  # idempotent


@pytest.mark.gui
@pytest.mark.render
def test_app_starts_renders_and_exits_cleanly(tmp_path: Path) -> None:
    env = {"EVE_HOME": str(tmp_path / "home"), "PYTHONPATH": str(ROOT / "src")}
    import os

    full_env = {**os.environ, **env}
    shot = tmp_path / "frame.png"
    proc = subprocess.run(
        [sys.executable, "-m", "eve", "--demo", "--smoke-test", "4", "--screenshot", str(shot)],
        capture_output=True,
        text=True,
        timeout=90,
        env=full_env,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    report = json.loads(proc.stdout[proc.stdout.index("{") :])
    assert report["frames"] > 60
    assert report["frame_ms_p95"] < 30
    assert report["screenshot_saved"] is True and shot.stat().st_size > 1000
    # settings were written to the temporary home, not the source tree
    assert (tmp_path / "home" / "config" / "settings.json").exists()
    assert not (ROOT / "settings.json").exists()


@pytest.mark.gui
def test_second_instance_is_refused(tmp_path: Path) -> None:
    import os

    env = {**os.environ, "EVE_HOME": str(tmp_path / "home"), "PYTHONPATH": str(ROOT / "src")}
    first = subprocess.Popen(
        [sys.executable, "-m", "eve", "--no-audio", "--smoke-test", "6"],
        env=env,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        import time

        lock = tmp_path / "home" / "config" / "eve.lock"
        deadline = time.monotonic() + 30
        while not lock.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert lock.exists()
        second = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from PySide6.QtWidgets import QMessageBox; QMessageBox.information = lambda *a, **k: 0; "
                "from eve.main import main; sys.exit(main(['--no-audio']))",
            ],
            env=env,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert second.returncode == 3
        assert "already running" in second.stderr
    finally:
        first.wait(timeout=60)
    assert first.returncode == 0
