"""Setup progress reporting and dependency validation (stdlib-only setup package)."""

from __future__ import annotations

import io
from pathlib import Path

from setup import dependency_checker as deps
from setup import environment_manager as envm
from setup.progress import DONE, FAILED, ProgressReporter, SetupStep, TerminalRenderer


def steps() -> list[SetupStep]:
    return [SetupStep("a", "A", 1), SetupStep("b", "B", 8), SetupStep("c", "C", 1)]


def test_progress_reflects_completed_work_only() -> None:
    r = ProgressReporter(steps())
    assert r.percent == 0
    r.start("a")
    r.complete("a")
    assert r.percent == 10
    r.start("b")
    r.update("b", 0.5)
    assert r.percent == 50
    r.update("b", 0.2)  # never moves backwards
    assert r.percent == 50
    r.complete("b")
    r.start("c")
    r.update("c", 1.0)
    assert r.percent == 99  # not 100 until the step reports success
    r.complete("c")
    assert r.percent == 100


def test_failure_is_recorded_and_not_complete() -> None:
    r = ProgressReporter(steps())
    r.start("a")
    r.fail("a", "network down")
    assert r.failed
    assert r.steps[0].state == FAILED
    assert r.percent < 100


def test_skip_counts_as_done() -> None:
    r = ProgressReporter(steps())
    for key in ("a", "b", "c"):
        r.skip(key, "already done")
    assert r.percent == 100


def test_terminal_renderer_plain_mode_writes_lines() -> None:
    out = io.StringIO()
    renderer = TerminalRenderer(out)
    r = ProgressReporter(steps(), renderer)
    r.start("a")
    r.complete("a")
    text = out.getvalue()
    assert "A: running" in text and "A: done" in text
    assert r.steps[0].state == DONE


def test_parse_requirements_with_markers_and_includes(tmp_path: Path) -> None:
    (tmp_path / "base.txt").write_text('numpy==2.0.0\nfoo-bar==1.2 ; sys_platform == "darwin"\n# c\n')
    (tmp_path / "dev.txt").write_text("-r base.txt\npytest==8.0.0\nwinonly==1.0; sys_platform == 'win32'\n")
    mac = deps.parse_requirements(tmp_path / "dev.txt", sys_platform="darwin")
    linux = deps.parse_requirements(tmp_path / "dev.txt", sys_platform="linux")
    assert [r.name for r in mac] == ["numpy", "foo-bar", "pytest"]
    assert [r.name for r in linux] == ["numpy", "pytest"]


def test_project_requirements_are_all_exact_pins() -> None:
    root = Path(__file__).resolve().parents[2]
    for platform in ("darwin", "win32", "linux"):
        reqs = deps.parse_requirements(root / "requirements.txt", sys_platform=platform)
        assert reqs and all(r.version for r in reqs)
    assert any(r.name.startswith("pyobjc") for r in deps.parse_requirements(root / "requirements.txt", "darwin"))
    assert not any(r.name.startswith("pyobjc") for r in deps.parse_requirements(root / "requirements.txt", "win32"))


def test_find_mismatches_normalizes_names() -> None:
    reqs = [deps.Requirement("PySide6_Essentials", "6.12.0"), deps.Requirement("numpy", "2.5.4")]
    installed = {"pyside6-essentials": "6.12.0", "numpy": "2.0.0"}
    problems = deps.find_mismatches(reqs, installed)
    assert [(r.name, have) for r, have in problems] == [("numpy", "2.0.0")]


def test_fingerprint_changes_with_requirements_and_python(tmp_path: Path) -> None:
    f = tmp_path / "requirements.txt"
    f.write_text("numpy==1.0\n")
    a = deps.requirements_fingerprint([f], (3, 12), "darwin")
    assert a == deps.requirements_fingerprint([f], (3, 12, 9), "darwin")
    assert a != deps.requirements_fingerprint([f], (3, 13), "darwin")
    f.write_text("numpy==1.1\n")
    assert a != deps.requirements_fingerprint([f], (3, 12), "darwin")


def test_supported_python_range() -> None:
    assert envm.is_supported_version((3, 12, 1))
    assert envm.is_supported_version((3, 11, 0))
    assert not envm.is_supported_version((3, 10, 9))
    assert not envm.is_supported_version((3, 14, 0))


def test_network_error_detection() -> None:
    assert envm.looks_like_network_error("WARNING: Retrying ... NewConnectionError(...)")
    assert envm.looks_like_network_error("ERROR: No matching distribution found for numpy==2.5.4")
    assert not envm.looks_like_network_error("ERROR: Failed building wheel for foo")
