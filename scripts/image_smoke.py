"""Exercise a built instance image using only uniquely named disposable resources."""

import argparse
import json
import sys
import time
from collections.abc import Sequence
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from uuid import uuid4

from przepisnik.constants import IPV4_LOOPBACK, IPV4_WILDCARD, PROJECT_NAME
from scripts.command_runner import CommandRunner

STARTUP_TIMEOUT_SECONDS = 180
POLL_SECONDS = 1
IMAGE_USER_ID = "10001"
ROOT_USER_ID = 0
AUTHORITY = "ci.przepisnik.invalid:8000"


class ImageSmoke:
    """Validate startup guards and recipe/photo persistence for one built image."""

    def __init__(self, image: str, artifacts: Path) -> None:
        """Configure a self-contained smoke run.

        Args:
            image: Explicit prebuilt local image ID.
            artifacts: Fresh location for configuration and diagnostic logs.

        Returns:
            None: Initializes uniquely named resources without touching an instance.
        """
        self._image = image
        self._artifacts = artifacts.resolve()
        self._name = f"{PROJECT_NAME}-smoke-{uuid4().hex}"
        self._volume = f"{self._name}-data"
        self._docker = CommandRunner("docker")
        self._reject_names: list[str] = []
        return None

    def _start(self) -> int:
        """Start the same image/volume and return its ephemeral loopback host port.

        Returns:
            int: Published browser port after Docker reports a healthy application.
        """
        config_file = self._artifacts / "server.toml"
        self._docker.run(
            [
                "run",
                "--detach",
                "--pull=never",
                "--name",
                self._name,
                "--publish",
                f"{IPV4_LOOPBACK}::8000",
                "--mount",
                f"type=volume,source={self._volume},target=/data",
                "--mount",
                f"type=bind,source={config_file},target=/config/server.toml,readonly",
                "--env",
                "PRZEPISNIK_CONFIG=/config/server.toml",
                self._image,
            ]
        )
        deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            state = self._docker.run(
                [
                    "inspect",
                    "--format",
                    "{{.State.Running}} {{.State.Health.Status}}",
                    self._name,
                ]
            ).stdout.strip()
            if state == "true healthy":
                ports = self._docker.run(
                    [
                        "inspect",
                        "--format",
                        "{{json .NetworkSettings.Ports}}",
                        self._name,
                    ]
                ).stdout
                return int(json.loads(ports)["8000/tcp"][0]["HostPort"])
            if state.startswith("false ") or state.endswith(" unhealthy"):
                health = self._docker.run(
                    ["inspect", "--format", "{{json .State.Health}}", self._name], check=False
                )
                (self._artifacts / "health.log").write_text(
                    health.stdout + health.stderr, encoding="utf-8"
                )
                raise RuntimeError(f"Image startup failed: {state}")
            time.sleep(POLL_SECONDS)
        raise RuntimeError("Image startup timed out")

    @staticmethod
    def _request(port: int, payload: dict[str, object] | None = None) -> dict[str, object]:
        """Call the recipe API with its custom configured host and origin.

        Args:
            port: Docker's ephemeral loopback port.
            payload: Optional recipe-creation document.

        Returns:
            dict[str, object]: Decoded successful JSON response.
        """
        headers = {"Host": AUTHORITY, "Origin": f"http://{AUTHORITY}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        method = "GET" if payload is None else "POST"
        body = None if payload is None else json.dumps(payload)
        with closing(HTTPConnection(IPV4_LOOPBACK, port, timeout=10)) as client:
            client.request(method, "/api/recipes", body=body, headers=headers)
            response = client.getresponse()
            content = response.read()
            if response.status != (200 if payload is None else 201):
                raise RuntimeError(f"Unexpected recipe API status: {response.status}")
        result: dict[str, object] = json.loads(content)
        return result

    def _reject(
        self, directory: Path, message: str, *, readonly: bool = False, config: str | None = None
    ) -> None:
        """Require an unsafe start to fail while preserving the mounted sentinel.

        Args:
            directory: Disposable host-owned source/data directory.
            message: Expected entrypoint rejection message.
            readonly: Whether the data mount should be read-only.
            config: Optional explicitly missing configuration path.

        Returns:
            None: The bounded foreground run failed with the expected diagnostic.
        """
        name = f"{self._name}-reject-{len(self._reject_names)}"
        self._reject_names.append(name)
        arguments = ["run", "--rm", "--pull=never", "--name", name]
        if sys.platform != "win32":
            ownership = directory.stat()
            if ownership.st_uid == ROOT_USER_ID:
                raise RuntimeError("Smoke bind tests require a non-root Linux data owner")
            arguments.extend(["--user", f"{ownership.st_uid}:{ownership.st_gid}"])
        suffix = ",readonly" if readonly else ""
        arguments.extend(["--mount", f"type=bind,source={directory},target=/data{suffix}"])
        if config is not None:
            arguments.extend(["--env", f"PRZEPISNIK_CONFIG={config}"])
        result = self._docker.run([*arguments, self._image], check=False)
        if result.returncode == 0 or message not in result.stdout + result.stderr:
            raise RuntimeError(f"Startup guard failed: {message}")
        return None

    def _guards(self) -> None:
        """Check missing config, read-only data and both legacy-data guards.

        Returns:
            None: No guard created a database or altered the sentinel recipe.
        """
        empty = self._artifacts / "empty"
        empty.mkdir()
        self._reject(
            empty, "Server configuration must be a readable file", config="/missing/server.toml"
        )
        self._reject(empty, "Data directory must exist and be writable", readonly=True)
        recipe = empty / "recipes/legacy/recipe.json"
        recipe.parent.mkdir(parents=True)
        recipe.write_text('{"title":"Sentinel"}', encoding="utf-8")
        self._reject(empty, "Legacy data found")
        if (
            recipe.read_text(encoding="utf-8") != '{"title":"Sentinel"}'
            or (empty / "recipes.sqlite3").exists()
        ):
            raise RuntimeError("Legacy guard modified the source collection")
        sources = self._artifacts / "sources-only"
        sources.mkdir()
        (sources / "sources.json").write_text("{}", encoding="utf-8")
        self._reject(sources, "Legacy data found")
        return None

    def _container_command(self, *arguments: str) -> str:
        """Execute a checked command only inside this smoke test's container.

        Args:
            arguments: Explicit executable and argument vector inside the container.

        Returns:
            str: Captured command output.
        """
        return self._docker.run(["exec", self._name, *arguments]).stdout

    def verify(self) -> None:
        """Test the instance using a fresh volume, then clean up only owned resources.

        Returns:
            None: All smoke assertions and required Docker commands succeeded.
        """
        self._artifacts.mkdir(parents=True, exist_ok=False)
        (self._artifacts / "server.toml").write_text(
            f'host = "{IPV4_WILDCARD}"\nport = 8000\norigins = ["http://{AUTHORITY}"]\n',
            encoding="utf-8",
        )
        try:
            self._docker.run(["volume", "create", self._volume])
            port = self._start()
            uid = self._container_command("id", "-u").strip()
            if uid != IMAGE_USER_ID or self._request(port).get("total") != 0:
                raise RuntimeError("Image must start empty and as the configured non-root user")
            self._container_command("test", "!", "-d", "/app/docker/demo/recipes")
            self._guards()
            family = {
                "servings": 1,
                "ingredients": [{"name": "Water", "amount": 1, "unit": "l"}],
            }
            recipe = {
                "title": "CI persistence",
                "steps": ["Keep after recreation."],
                "variants": {"family": family},
            }
            self._request(port, {"recipe": recipe})
            copy_photo = (
                "import shutil; shutil.copyfile('/data/empty_dish.png', '/data/ci-photo.png')"
            )
            self._container_command("/app/.venv/bin/python", "-c", copy_photo)
            self._docker.run(["rm", "--force", self._name])
            port = self._start()
            if self._request(port).get("total") != 1:
                raise RuntimeError("Recipe did not survive container recreation")
            check_photo = (
                "from pathlib import Path; "
                "assert Path('/data/ci-photo.png').read_bytes() == "
                "Path('/data/empty_dish.png').read_bytes()"
            )
            self._container_command("/app/.venv/bin/python", "-c", check_photo)
            self._container_command(
                "/app/.venv/bin/przepisnik", "--data-dir", "/data", "check-data"
            )
            (self._artifacts / "result.json").write_text(
                json.dumps({"image": self._image, "passed": True}), encoding="utf-8"
            )
        finally:
            logs = self._docker.run(["logs", self._name], check=False)
            (self._artifacts / "container.log").write_text(
                logs.stdout + logs.stderr, encoding="utf-8"
            )
            for name in [self._name, *self._reject_names]:
                self._docker.run(["rm", "--force", name], check=False)
            self._docker.run(["volume", "rm", self._volume], check=False)
        return None


def main(argv: Sequence[str] | None = None) -> None:
    """Run one image smoke test selected by CLI.

    Args:
        argv: Optional CLI arguments.

    Returns:
        None: The instance passed; exceptions fail the CI command.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args(argv)
    ImageSmoke(args.image, args.artifacts).verify()
    return None


if __name__ == "__main__":
    main()
