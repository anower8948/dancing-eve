"""SetupManager orchestration with the slow/networked operations replaced by fakes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from setup import environment_manager as envm
from setup import setup_manager as sm
from setup.platform_detector import detect_platform
from setup.progress import DONE, SKIPPED, ProgressReporter


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "requirements.txt").write_text("numpy==9.9.9\n")
    return tmp_path


def make_manager(
    project: Path, monkeypatch: pytest.MonkeyPatch, pip_results: list[tuple[int, str]], interactive_answer: bool = False
):
    py = envm.PythonCandidate((sys.executable,), (3, 12, 0), sys.executable)
    state = {"installed": {}, "pip_calls": 0}

    monkeypatch.setattr(envm, "inspect_venv", lambda d: py if (d / "pyvenv.cfg").exists() else None)
    monkeypatch.setattr(envm, "find_python_candidates", lambda system, include_current=True: [py])

    def fake_create(python, venv_dir, log):
        venv_dir.mkdir(parents=True, exist_ok=True)
        (venv_dir / "pyvenv.cfg").write_text("home = x\n")

    def fake_pip(python, args, log, on_package=None, on_installing=None, env=None):
        state["pip_calls"] += 1
        code, output = pip_results.pop(0)
        if code == 0:
            if on_package:
                on_package("numpy")
            state["installed"] = {"numpy": "9.9.9"}
        return code, output

    monkeypatch.setattr(envm, "create_venv", fake_create)
    monkeypatch.setattr(envm, "run_pip", fake_pip)
    monkeypatch.setattr(sm.deps, "installed_versions", lambda python: dict(state["installed"]))
    monkeypatch.setattr(sm.deps, "validate_imports", lambda python, modules: [])
    monkeypatch.setattr(sm.time, "sleep", lambda s: None)
    monkeypatch.setattr(sm.SetupManager, "step_audio", lambda self, key: self.reporter.complete(key, "skipped in test"))

    reporter = ProgressReporter(sm.default_steps())
    messages: list[str] = []
    options = sm.SetupOptions(launch=False, interactive=True)
    manager = sm.SetupManager(
        project,
        reporter,
        options,
        log=lambda s: None,
        say=messages.append,
        ask=lambda q: interactive_answer,
        platform_info=detect_platform(),
    )
    return manager, reporter, state, messages


def test_first_run_installs_then_second_run_reuses(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, reporter, state, _ = make_manager(project, monkeypatch, [(0, "ok")])
    assert manager.run() == 0
    assert reporter.percent == 100 or reporter.steps[-1].state == SKIPPED
    assert state["pip_calls"] == 1
    assert (project / ".venv" / sm.MARKER_NAME).exists()

    manager2, reporter2, state2, _ = make_manager(project, monkeypatch, [])
    state2["installed"] = {"numpy": "9.9.9"}
    assert manager2.run() == 0
    by_key = {s.key: s.state for s in reporter2.steps}
    assert by_key["venv"] == SKIPPED and by_key["deps"] == SKIPPED
    assert state2["pip_calls"] == 0


def test_network_failure_retries_then_succeeds(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    failure = (1, "ERROR: Could not fetch URL https://pypi.org/simple/numpy/: connection error")
    manager, reporter, state, _ = make_manager(project, monkeypatch, [failure, (0, "ok")])
    assert manager.run() == 0
    assert state["pip_calls"] == 2
    assert {s.key: s.state for s in reporter.steps}["deps"] == DONE


def test_persistent_network_failure_reports_step_and_keeps_venv(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    failure = (1, "Temporary failure in name resolution")
    manager, reporter, state, messages = make_manager(project, monkeypatch, [failure] * 3, interactive_answer=False)
    code = manager.run()
    assert code == 4
    assert reporter.failed
    assert any("Installing dependencies" in m for m in messages)
    assert any("network" in m.lower() for m in messages)
    assert (project / ".venv" / "pyvenv.cfg").exists()  # completed work preserved
    assert not (project / ".venv" / sm.MARKER_NAME).exists()  # never marked installed


def test_setup_lock_prevents_concurrent_runs(tmp_path: Path) -> None:
    lock_a = sm.SetupLock(tmp_path / "setup.lock")
    lock_b = sm.SetupLock(tmp_path / "setup.lock")
    assert lock_a.acquire()
    assert not lock_b.acquire()
    lock_a.release()
    assert lock_b.acquire()
    lock_b.release()


def test_stale_lock_is_recovered(tmp_path: Path) -> None:
    (tmp_path / "setup.lock").write_text("999999999")  # no such process
    assert sm.SetupLock(tmp_path / "setup.lock").acquire()
