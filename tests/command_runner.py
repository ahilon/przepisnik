"""Shared, shell-free command execution for Windows and Linux test helpers."""

import shutil
import subprocess
from collections.abc import Sequence

DEFAULT_COMMAND_TIMEOUT_SECONDS = 30


class CommandRunner:
    """Resolve one executable and run bounded commands with separate output streams."""

    def __init__(
        self, executable: str, *, timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS
    ) -> None:
        """Resolve the executable once using the current process environment.

        Args:
            executable: Executable name or path accepted by shutil.which.
            timeout: Maximum duration of each command, in seconds.

        Returns:
            None: Stores the resolved executable and timeout.

        Raises:
            FileNotFoundError: If the requested executable is unavailable.
        """
        resolved = shutil.which(executable)
        if resolved is None:
            raise FileNotFoundError(f"Executable not found: {executable}")
        self._executable: str = resolved
        self._timeout: float = timeout
        return None

    def run(
        self, arguments: Sequence[str], *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Run separated arguments without a shell, preserving stdout and stderr.

        Args:
            arguments: Arguments passed directly to the resolved executable.
            check: Whether a nonzero exit status raises CalledProcessError.

        Returns:
            subprocess.CompletedProcess[str]: Exit status and decoded output streams.

        Raises:
            OSError: If the executable cannot be started.
            subprocess.CalledProcessError: If a checked command exits unsuccessfully.
            subprocess.TimeoutExpired: If execution exceeds the configured timeout.
        """
        return subprocess.run(
            [self._executable, *arguments],
            check=check,
            shell=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=self._timeout,
        )
