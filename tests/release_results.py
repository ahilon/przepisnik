"""Record strict selected-test outcomes without accepting skips or expected failures."""

import json
from pathlib import Path

import pytest


class ReleaseResults:
    """Capture each test identity once and write a machine-readable release gate."""

    def __init__(self, output: Path) -> None:
        """Bind the summary file without changing normal pytest output.

        Args:
            output: Destination used only when explicitly selected by the caller.

        Returns:
            None: Initializes outcome sets for this pytest session.
        """
        self._output = output
        self._passed: set[str] = set()
        self._failed: set[str] = set()
        self._skipped: set[str] = set()
        self._xfailed: set[str] = set()
        return None

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Track calls and setup/teardown failures, including non-strict xpasses.

        Args:
            report: One pytest phase outcome for a selected test.

        Returns:
            None: Updates identity sets without counting setup as a passed test.
        """
        if hasattr(report, "wasxfail"):
            self._xfailed.add(report.nodeid)
        elif report.failed:
            self._failed.add(report.nodeid)
        elif report.skipped:
            self._skipped.add(report.nodeid)
        elif report.when == "call" and report.passed:
            self._passed.add(report.nodeid)
        return None

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Persist selected-test counts, including collection/internal error status.

        Args:
            session: Completed pytest session.
            exitstatus: Final pytest status supplied by the runner.

        Returns:
            None: Writes a summary suitable for strict release validation.
        """
        result = {
            "collected": session.testscollected,
            "passed": len(self._passed),
            "failed": len(self._failed),
            "skipped": len(self._skipped),
            "xfailed": len(self._xfailed),
            "exit_code": int(exitstatus),
        }
        self._output.parent.mkdir(parents=True, exist_ok=True)
        self._output.write_text(json.dumps(result), encoding="utf-8")
        return None
