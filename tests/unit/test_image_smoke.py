"""Check smoke orchestration and real HTTP boundaries without a Docker daemon."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest
from scripts.image_smoke import ImageSmoke


def test_smoke_recreates_same_image_and_always_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise startup guards, persistence orchestration and owned-resource cleanup.

    Args:
        tmp_path: Disposable artifacts.
        monkeypatch: Docker process and HTTP boundaries.

    Returns:
        None: The same image/volume is recreated and cleanup targets only test resources.
    """

    def docker(arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Simulate only Docker I/O while retaining smoke assertions.

        Args:
            arguments: Docker command arguments.
            check: Caller error policy.

        Returns:
            subprocess.CompletedProcess[str]: Expected image or startup-guard response.
        """
        del check
        if arguments[0] == "inspect":
            output = "true healthy"
            if "{{json .NetworkSettings.Ports}}" in arguments:
                output = json.dumps({"8000/tcp": [{"HostPort": "8123"}]})
            return subprocess.CompletedProcess(arguments, 0, output, "")
        if arguments[0] == "run" and "--detach" not in arguments:
            if any("/missing/server.toml" in part for part in arguments):
                message = "Server configuration must be a readable file"
            elif any("readonly" in part for part in arguments):
                message = "Data directory must exist and be writable"
            else:
                message = "Legacy data found"
            return subprocess.CompletedProcess(arguments, 1, "", message)
        output = "10001" if arguments[-2:] == ["id", "-u"] else ""
        return subprocess.CompletedProcess(arguments, 0, output, "")

    runner = MagicMock()
    runner.run.side_effect = docker
    monkeypatch.setattr("scripts.image_smoke.CommandRunner", MagicMock(return_value=runner))
    monkeypatch.setattr("scripts.image_smoke.sys.platform", "win32")
    requests = MagicMock(side_effect=[{"total": 0}, {"id": "created"}, {"total": 1}])
    monkeypatch.setattr(ImageSmoke, "_request", requests)
    output = tmp_path / "smoke"
    ImageSmoke("sha256:test-image", output).verify()
    assert json.loads((output / "result.json").read_text())["passed"] is True
    starts = [call.args[0] for call in runner.run.call_args_list if "--detach" in call.args[0]]
    assert len(starts) == 2
    assert starts[0] == starts[1]
    assert starts[0][-1] == "sha256:test-image"
    assert runner.run.call_args.args[0][:2] == ["volume", "rm"]


@pytest.mark.parametrize("state", ["false starting", "true unhealthy"])
def test_failed_smoke_start_removes_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """Fail readiness without proceeding to persistence/publication.

    Args:
        tmp_path: Disposable artifact directory.
        monkeypatch: Scoped Docker process boundary.
        state: Failed Docker running/health status.

    Returns:
        None: Startup failure still executes named-volume cleanup.
    """
    runner = MagicMock()
    runner.run.return_value = subprocess.CompletedProcess([], 0, state, "")
    monkeypatch.setattr("scripts.image_smoke.CommandRunner", MagicMock(return_value=runner))
    with pytest.raises(RuntimeError, match="startup failed"):
        ImageSmoke("local-image", tmp_path / "smoke").verify()
    assert runner.run.call_args.args[0][:2] == ["volume", "rm"]
    assert not (tmp_path / "smoke/result.json").exists()


def test_http_probe_uses_configured_host_and_real_statuses(
    app_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise real HTTP status/body handling against isolated test application data.

    Args:
        app_url: Fresh local application from repository fixtures.
        monkeypatch: Explicit allowed authority for this loopback server.

    Returns:
        None: Reads, creation and rejection work through the smoke HTTP client.
    """
    address = urlsplit(app_url)
    assert address.port is not None
    monkeypatch.setattr("scripts.image_smoke.AUTHORITY", address.netloc)
    assert ImageSmoke._request(address.port)["total"] == 6
    family = {"servings": 1, "ingredients": [{"name": "Water", "amount": 1, "unit": "l"}]}
    recipe = {"title": "Smoke API", "steps": ["Mix"], "variants": {"family": family}}
    created = ImageSmoke._request(address.port, {"recipe": recipe})
    assert "id" in created
    with pytest.raises(RuntimeError, match="status"):
        ImageSmoke._request(address.port, {})
