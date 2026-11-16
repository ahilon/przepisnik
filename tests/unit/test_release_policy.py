"""Exercise release selection and strict test gates independently of GitHub."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, cast
from unittest.mock import MagicMock

import pytest
from release_results import ReleaseResults
from scripts.release import append_output, main, package_version
from scripts.release_policy import ChangeDetector, affects_image, verify_results

BEFORE = "1" * 40
AFTER = "2" * 40
type ReportPhase = Literal["setup", "call", "teardown"]
type TestOutcome = Literal["passed", "failed", "skipped"]


@pytest.mark.parametrize(
    "path,expected",
    [
        ("README.md", False),
        ("docker/README.md", False),
        ("docs/setup.txt", False),
        (".agents/skills/tool/SKILL.md", False),
        ("tools/respo/import_recipes.py", False),
        ("src/przepisnik/web/server.py", True),
        ("tests/e2e/test_shopping.py", True),
        ("scripts/release.py", True),
        ("docker/Dockerfile", True),
        ("docker/demo/placeholder.png", True),
        (".github/workflows/release.yml", True),
    ],
)
def test_runtime_file_selection(path: str, expected: bool) -> None:
    """Select application/release inputs while ignoring documentation-only paths.

    Args:
        path: Changed repository path.
        expected: Whether the path can require a new tested image.

    Returns:
        None: The expected release decision was asserted.
    """
    assert affects_image(path) is expected


def test_metadata_version_bumps_do_not_hide_dependency_changes() -> None:
    """Skip doc-only version bumps while preserving real dependency/tool changes.

    Returns:
        None: Only the local project's version is excluded from comparison.
    """
    before = '[project]\nname="app"\nversion="1.0.0"\ndependencies=["pydantic==2"]\n'
    after = before.replace("1.0.0", "1.0.1")
    assert not affects_image("pyproject.toml", before, after)
    assert affects_image("pyproject.toml", before, after.replace("pydantic==2", "pydantic==3"))
    lock = (
        '[[package]]\nname="app"\nversion="1.0.0"\nsource={editable="."}\n'
        '[[package]]\nname="dep"\nversion="2.0.0"\n'
    )
    assert not affects_image("uv.lock", lock, lock.replace("1.0.0", "1.0.1"))
    assert affects_image("uv.lock", lock, lock.replace("2.0.0", "3.0.0"))
    assert affects_image("pyproject.toml", before, None)


def test_git_comparison_reads_metadata_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use committed contents rather than assuming every pyproject edit changes code.

    Args:
        monkeypatch: Scoped Git process boundary.

    Returns:
        None: Semantic comparison, absent metadata, SHA validation and Git errors were checked.
    """
    runner = MagicMock()
    runner.run.side_effect = [
        subprocess.CompletedProcess([], 0, "README.md\0pyproject.toml\0"),
        subprocess.CompletedProcess([], 0, ""),
        subprocess.CompletedProcess([], 0, '[project]\nversion="1.0.0"'),
        subprocess.CompletedProcess([], 0, ""),
        subprocess.CompletedProcess([], 0, '[project]\nversion="1.0.1"'),
    ]
    monkeypatch.setattr("scripts.release_policy.CommandRunner", MagicMock(return_value=runner))
    detector = ChangeDetector()
    assert not detector.changed(BEFORE, AFTER)
    runner.run.side_effect = [
        subprocess.CompletedProcess([], 0, "pyproject.toml\0"),
        subprocess.CompletedProcess([], 1, ""),
        subprocess.CompletedProcess([], 1, ""),
    ]
    assert detector.changed(BEFORE, AFTER)
    assert detector.changed("0" * 40, AFTER)
    with pytest.raises(ValueError, match="SHAs"):
        detector.changed("--unsafe", AFTER)
    runner.run.side_effect = subprocess.CalledProcessError(128, "git")
    with pytest.raises(subprocess.CalledProcessError):
        detector.changed(BEFORE, AFTER)


@pytest.mark.parametrize(
    "field,value",
    [
        ("collected", 0),
        ("passed", 1),
        ("failed", 1),
        ("skipped", 1),
        ("xfailed", 1),
        ("exit_code", 1),
        ("collected", True),
        ("passed", -1),
    ],
)
def test_only_complete_selected_test_passes_are_accepted(
    tmp_path: Path, field: str, value: int
) -> None:
    """Reject empty runs, all failure modes and malformed numeric counts.

    Args:
        tmp_path: Temporary report directory.
        field: Count/status to corrupt.
        value: Invalid or non-passing value.

    Returns:
        None: The changed result cannot authorize publication.
    """
    report = {"collected": 2, "passed": 2, "failed": 0, "skipped": 0, "xfailed": 0, "exit_code": 0}
    path = tmp_path / "results.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    verify_results(path)
    report[field] = value
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_results(path)


@pytest.mark.parametrize("report", ["{}", "[]", "null", "not JSON"])
def test_malformed_test_reports_are_rejected(tmp_path: Path, report: str) -> None:
    """Do not infer success from missing or unparsable summary fields.

    Args:
        tmp_path: Temporary report directory.
        report: Invalid JSON or schema.

    Returns:
        None: An invalid summary fails the gate.
    """
    path = tmp_path / "report.json"
    path.write_text(report, encoding="utf-8")
    with pytest.raises(ValueError):
        verify_results(path)


def test_collector_includes_phase_failures_and_empty_reason_xpass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Track calls once and reject xpasses even when their reason is empty.

    Args:
        tmp_path: Temporary summary directory.
        monkeypatch: Scoped xpass marker on the synthetic report.

    Returns:
        None: All selected outcome categories and the final status are preserved.
    """
    path = tmp_path / "results/summary.json"
    collector = ReleaseResults(path)
    reports: list[tuple[str, ReportPhase, TestOutcome, bool]] = [
        ("pass", "setup", "passed", False),
        ("pass", "call", "passed", False),
        ("pass", "teardown", "passed", False),
        ("error", "setup", "failed", False),
        ("skip", "setup", "skipped", False),
        ("xpass", "call", "passed", True),
    ]
    for nodeid, when, outcome, xpass in reports:
        report = pytest.TestReport(
            nodeid=nodeid,
            location=("test.py", 1, nodeid),
            keywords={},
            outcome=outcome,
            longrepr=None,
            when=when,
        )
        if xpass:
            monkeypatch.setattr(report, "wasxfail", "", raising=False)
        collector.pytest_runtest_logreport(report)
    collector.pytest_sessionfinish(cast(pytest.Session, SimpleNamespace(testscollected=4)), 1)
    assert json.loads(path.read_text()) == {
        "collected": 4,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "xfailed": 1,
        "exit_code": 1,
    }


def test_cli_outputs_and_eligibility_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expose deterministic workflow outputs and validate package versions.

    Args:
        tmp_path: Temporary GitHub output file location.
        monkeypatch: Scoped change detector and project metadata.

    Returns:
        None: Publication eligibility is the inverse of newer runtime changes.
    """
    detector = MagicMock()
    detector.changed.return_value = False
    monkeypatch.setattr("scripts.release.ChangeDetector", MagicMock(return_value=detector))
    output = tmp_path / "output"
    arguments = ["eligibility", "--before", BEFORE, "--after", AFTER]
    assert main([*arguments, "--github-output", str(output)]) == 0
    assert "eligible=true" in output.read_text()
    detector.changed.return_value = True
    assert main(["changes", "--before", BEFORE, "--after", AFTER]) == 0
    with pytest.raises(ValueError):
        append_output(output, "unsafe", "value\nother=value")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="1.11.1"')
    assert package_version() == "1.11.1"
    assert main(["version", "--github-env", str(output)]) == 0
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="unsafe"')
    with pytest.raises(ValueError):
        package_version()
    assert main(["verify-tests", str(tmp_path / "missing")]) == 1
