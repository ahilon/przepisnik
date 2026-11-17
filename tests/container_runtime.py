"""Run isolated browser-test instances from an already built Docker image."""

import logging
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from socket import socket
from sys import platform
from time import monotonic, sleep
from uuid import uuid4

from scripts.command_runner import CommandRunner

from przepisnik.constants import IPV4_LOOPBACK, IPV4_WILDCARD, PROJECT_NAME

logger = logging.getLogger(__name__)
CONTAINER_PORT = 8000
START_TIMEOUT_SECONDS = 90
POLL_INTERVAL_SECONDS = 0.25
# POSIX UID 0 is the superuser; explicit root execution is never a test default.
ROOT_USER_ID = 0


class ContainerApplication:
    """Own one disposable container and its configuration for a test's data."""

    def __init__(
        self,
        data_dir: Path,
        image: str,
        artifacts_dir: Path,
        *,
        user: tuple[int, int] | None = None,
        timeout: float = START_TIMEOUT_SECONDS,
    ) -> None:
        """Configure an isolated container without starting it.

        Pass optional lifecycle overrides by name, such as user=... or timeout=....

        Args:
            data_dir: Disposable SQLite/photo directory shared with test fixtures.
            image: Explicit, already built local image tag or digest.
            artifacts_dir: Directory for container logs, normally test-results.
            user: Optional UID/GID override. Windows otherwise keeps the image user;
                Linux uses the data owner so host fixtures retain write access.
            timeout: Maximum time to wait for image readiness, in seconds.

        Returns:
            None: Stores this test's lifecycle settings.
        """
        try:
            self._commands = CommandRunner("docker")
        except FileNotFoundError as error:
            message = "Container E2E require the Docker CLI and a running daemon"
            raise RuntimeError(message) from error
        ownership = data_dir.stat()
        self._user = user
        if self._user is None and platform != "win32":
            self._user = (ownership.st_uid, ownership.st_gid)
        self._data_dir = data_dir.resolve()
        self._image = image
        self._artifacts_dir = artifacts_dir
        self._timeout = timeout
        self._name = f"{PROJECT_NAME}-e2e-{uuid4().hex}"
        self._config_file = self._data_dir.parent / f"{self._name}.toml"

    def _execute(self, arguments: list[str], *, check: bool = True) -> str:
        """Execute separated Docker arguments with bounded time and captured output.

        Args:
            arguments: Docker subcommand and its explicit arguments.
            check: Whether a nonzero exit status should raise an exception.

        Returns:
            str: Stripped standard output from Docker.

        Raises:
            subprocess.CalledProcessError: If a checked Docker command fails.
            subprocess.TimeoutExpired: If the command exceeds its time limit.
        """
        result = self._commands.run(arguments, check=check)
        if arguments[0] == "logs":
            return (result.stdout + result.stderr).strip()
        return result.stdout.strip()

    def _start(self) -> str:
        """Start the image on a loopback port with this test's writable data.

        Returns:
            str: Browser URL matching the generated allowed origin.

        Raises:
            RuntimeError: If the data owner would run the container as root.
        """
        user_arguments: list[str] = []
        if self._user is not None:
            uid, gid = self._user
            if uid == ROOT_USER_ID:
                raise RuntimeError("Container E2E require a non-root data owner")
            user_arguments = ["--user", f"{uid}:{gid}"]
        with socket() as reservation:
            reservation.bind((IPV4_LOOPBACK, 0))
            port: int = reservation.getsockname()[1]
        url = f"http://{IPV4_LOOPBACK}:{port}"
        self._config_file.write_text(
            f'host = "{IPV4_WILDCARD}"\nport = {CONTAINER_PORT}\norigins = ["{url}"]\n',
            encoding="utf-8",
        )
        self._execute(
            [
                "run",
                "--detach",
                "--pull=never",
                "--name",
                self._name,
                *user_arguments,
                "--publish",
                f"{IPV4_LOOPBACK}:{port}:{CONTAINER_PORT}",
                "--mount",
                f"type=bind,source={self._data_dir},target=/data",
                "--mount",
                f"type=bind,source={self._config_file},target=/config/server.toml,readonly",
                "--env",
                "PRZEPISNIK_CONFIG=/config/server.toml",
                self._image,
            ]
        )
        return url

    def _wait_ready(self) -> None:
        """Wait for the image healthcheck, failing on exit or unhealthy status.

        Returns:
            None: Docker reports a running, healthy instance.

        Raises:
            RuntimeError: If startup fails or never reaches a healthy state.
        """
        deadline = monotonic() + self._timeout
        while monotonic() < deadline:
            state = self._execute(
                ["inspect", "--format", "{{.State.Running}} {{.State.Health.Status}}", self._name]
            )
            if state == "true healthy":
                return None
            if state.startswith("false ") or state.endswith(" unhealthy"):
                raise RuntimeError(f"Container failed readiness: {state}")
            sleep(POLL_INTERVAL_SECONDS)
        raise RuntimeError("Container did not become healthy within the startup timeout")

    def _cleanup(self) -> None:
        """Save logs and remove only this helper's uniquely named container.

        Returns:
            None: Cleanup was attempted without masking the original test failure.
        """
        try:
            logs = self._execute(["logs", self._name], check=False)
            self._artifacts_dir.mkdir(parents=True, exist_ok=True)
            (self._artifacts_dir / f"{self._name}.log").write_text(logs, encoding="utf-8")
        except (OSError, subprocess.SubprocessError) as error:
            logger.warning("Could not collect container logs: %s", error)
        finally:
            try:
                self._execute(["rm", "--force", self._name], check=False)
            except (OSError, subprocess.SubprocessError) as error:
                logger.warning("Could not remove test container %s: %s", self._name, error)
        return None

    @contextmanager
    def running(self) -> Iterator[str]:
        """Start, wait for and always clean up a test instance.

        Yields:
            str: URL of the healthy container for browser navigation.
        """
        try:
            url = self._start()
            self._wait_ready()
            yield url
        finally:
            self._cleanup()
