"""Verify real cross-platform process boundaries without Docker or a shell."""

import subprocess
import sys
from unittest.mock import MagicMock

import pytest
from command_runner import CommandRunner


def test_arguments_remain_literal_and_output_streams_stay_separate() -> None:
    """Preserve spaces and shell metacharacters as one argument on either platform.

    Returns:
        None: The child received the literal value and both streams were captured.
    """
    literal = "two words; $HOME & literal"
    program = "import sys; print(sys.argv[1]); print('diagnostic', file=sys.stderr)"
    result = CommandRunner(sys.executable).run(["-c", program, literal])
    assert result.returncode == 0
    assert result.stdout.strip() == literal
    assert result.stderr.strip() == "diagnostic"


@pytest.mark.parametrize("check", [True, False])
def test_nonzero_exit_respects_the_callers_error_policy(check: bool) -> None:
    """Raise checked failures while preserving unchecked exit codes for diagnostics.

    Args:
        check: Whether a nonzero child exit status should raise an exception.

    Returns:
        None: The requested error policy and captured output were asserted.
    """
    runner = CommandRunner(sys.executable)
    arguments = ["-c", "import sys; print('failed'); sys.exit(5)"]
    if check:
        with pytest.raises(subprocess.CalledProcessError) as failure:
            runner.run(arguments)
        assert failure.value.returncode == 5
        assert failure.value.stdout.strip() == "failed"
        return None
    result = runner.run(arguments, check=False)
    assert result.returncode == 5
    assert result.stdout.strip() == "failed"
    return None


def test_missing_executable_fails_before_starting_a_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report unavailable executables during runner construction.

    Args:
        monkeypatch: Scoped replacement of executable lookup.

    Returns:
        None: No process can be started with an unresolved executable.
    """
    monkeypatch.setattr("command_runner.shutil.which", lambda _: None)
    with pytest.raises(FileNotFoundError, match="Executable not found"):
        CommandRunner("missing-command")


def test_timeout_is_bounded_and_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep command timeouts visible to the lifecycle helper's cleanup logic.

    Args:
        monkeypatch: Scoped simulated timeout at the subprocess boundary.

    Returns:
        None: The configured timeout and shell-free invocation were verified.
    """
    process = MagicMock(side_effect=subprocess.TimeoutExpired("command", 2))
    monkeypatch.setattr("command_runner.subprocess.run", process)
    runner = CommandRunner(sys.executable, timeout=2)
    with pytest.raises(subprocess.TimeoutExpired):
        runner.run(["--version"])
    assert process.call_args.kwargs["timeout"] == 2
    assert process.call_args.kwargs["shell"] is False
