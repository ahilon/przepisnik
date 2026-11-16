"""Test container fixture isolation and failure handling without invoking Docker."""

import subprocess
import tomllib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from container_runtime import ContainerApplication


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace only the subprocess boundary, retaining the real lifecycle helper.

    Args:
        monkeypatch: Scoped Docker executable and process replacements.

    Returns:
        MagicMock: A subprocess runner simulating a healthy container.
    """
    monkeypatch.setattr("command_runner.shutil.which", lambda _: "/usr/bin/docker")
    process = MagicMock(return_value=subprocess.CompletedProcess([], 0, "true healthy", ""))
    monkeypatch.setattr("command_runner.subprocess.run", process)
    return process


def test_container_uses_isolated_data_config_and_prebuilt_image(
    docker: MagicMock, tmp_path: Path
) -> None:
    """Verify isolation boundaries, no implicit pulls and configured browser origins.

    Args:
        docker: Fake Docker process boundary.
        tmp_path: Disposable bind-mount and log directory.

    Returns:
        None: Startup arguments, readiness and teardown were asserted.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    application = ContainerApplication(
        data_dir, "sha256:test-image", tmp_path / "logs", user=(1001, 1001)
    )
    with application.running() as url:
        configuration = next(tmp_path.glob("*.toml"))
        settings = tomllib.loads(configuration.read_text(encoding="utf-8"))
        assert settings["origins"] == [url]
        assert settings["port"] == 8000
        command = docker.call_args_list[0].args[0]
        assert command[:3] == ["/usr/bin/docker", "run", "--detach"]
        assert "--pull=never" in command
        assert command[command.index("--user") + 1] == "1001:1001"
        assert f"type=bind,source={data_dir.resolve()},target=/data" in command
        assert f"type=bind,source={configuration},target=/config/server.toml,readonly" in command
        assert command[-1] == "sha256:test-image"
        name = command[command.index("--name") + 1]
    assert docker.call_args.args[0] == ["/usr/bin/docker", "rm", "--force", name]
    assert len(list((tmp_path / "logs").glob("*.log"))) == 1


@pytest.mark.parametrize("state", ["false starting", "true unhealthy"])
def test_failed_readiness_cleans_up_and_never_yields_url(
    docker: MagicMock, tmp_path: Path, state: str
) -> None:
    """Reject exited/unhealthy containers and remove them after startup failure.

    Args:
        docker: Fake process boundary returning the specified readiness state.
        tmp_path: Disposable data/config/log directory.
        state: Docker running and health status fields.

    Returns:
        None: Startup fails and teardown removes the generated container.
    """
    docker.return_value.stdout = state
    application = ContainerApplication(
        tmp_path, "local-image", tmp_path / "logs", user=(1001, 1001)
    )
    with pytest.raises(RuntimeError, match="failed readiness"), application.running():
        pytest.fail("An unhealthy container must never be yielded")
    assert docker.call_args.args[0][1:3] == ["rm", "--force"]


def test_readiness_timeout_cleans_up(docker: MagicMock, tmp_path: Path) -> None:
    """Fail bounded startup rather than falling back to a host Python server.

    Args:
        docker: Fake Docker process boundary.
        tmp_path: Disposable test data and logs.

    Returns:
        None: The startup timeout fails and cleanup still runs.
    """
    application = ContainerApplication(
        tmp_path, "local-image", tmp_path / "logs", user=(1001, 1001), timeout=0
    )
    with pytest.raises(RuntimeError, match="startup timeout"), application.running():
        pytest.fail("Timed-out startup must never yield an application URL")
    assert docker.call_args.args[0][1:3] == ["rm", "--force"]


def test_browser_failure_still_collects_stderr_and_removes_container(
    docker: MagicMock, tmp_path: Path
) -> None:
    """Preserve browser failures while retaining both Docker log streams.

    Args:
        docker: Fake process boundary with application output on stderr.
        tmp_path: Disposable data/config/log directory.

    Returns:
        None: The original exception propagates after logs and cleanup.
    """
    docker.return_value.stderr = "application error on stderr"
    application = ContainerApplication(
        tmp_path, "local-image", tmp_path / "logs", user=(1001, 1001)
    )
    with pytest.raises(AssertionError, match="browser failure"), application.running():
        raise AssertionError("browser failure")
    log = next((tmp_path / "logs").glob("*.log"))
    assert "application error on stderr" in log.read_text(encoding="utf-8")
    assert docker.call_args.args[0][1:3] == ["rm", "--force"]


def test_root_owner_is_rejected_before_container_start(docker: MagicMock, tmp_path: Path) -> None:
    """Prevent a fixture ownership override from accidentally running as root.

    Args:
        docker: Fake process boundary, which must not start a container.
        tmp_path: Disposable data and logs.

    Returns:
        None: Root execution is rejected before Docker run.
    """
    application = ContainerApplication(tmp_path, "local-image", tmp_path / "logs", user=(0, 0))
    with pytest.raises(RuntimeError, match="non-root"), application.running():
        pytest.fail("Root-owned data must not start a container")
    assert all(call.args[0][1] != "run" for call in docker.call_args_list)


def test_missing_docker_fails_without_host_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit image selection must never silently test the host application.

    Args:
        monkeypatch: Scoped missing-executable simulation.
        tmp_path: Disposable data and log directory.

    Returns:
        None: Missing Docker is a clear setup failure.
    """
    monkeypatch.setattr("command_runner.shutil.which", lambda _: None)
    with pytest.raises(RuntimeError, match="Docker CLI"):
        ContainerApplication(tmp_path, "local-image", tmp_path / "logs")


def test_failed_docker_run_still_attempts_cleanup(docker: MagicMock, tmp_path: Path) -> None:
    """Remove a partially created container even when Docker run fails.

    Args:
        docker: Process boundary failing before readiness polling.
        tmp_path: Disposable data and diagnostic directory.

    Returns:
        None: Startup error propagates and cleanup is attempted.
    """
    docker.side_effect = [
        subprocess.CalledProcessError(125, ["docker", "run"]),
        subprocess.CompletedProcess([], 0, "startup diagnostic", ""),
        subprocess.CompletedProcess([], 0, "", ""),
    ]
    application = ContainerApplication(
        tmp_path, "local-image", tmp_path / "logs", user=(1001, 1001)
    )
    with pytest.raises(subprocess.CalledProcessError), application.running():
        pytest.fail("Failed Docker run must never yield a browser URL")
    assert docker.call_args.args[0][1:3] == ["rm", "--force"]
    log = next((tmp_path / "logs").glob("*.log"))
    assert log.read_text(encoding="utf-8") == "startup diagnostic"


def test_teardown_errors_preserve_original_browser_failure(
    docker: MagicMock, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Keep the useful test failure when Docker diagnostics and removal also fail.

    Args:
        docker: Process boundary with failing log collection and removal.
        tmp_path: Disposable data and diagnostic directory.
        caplog: Captured cleanup warnings.

    Returns:
        None: Browser failure propagates, with teardown failures recorded separately.
    """
    docker.side_effect = [
        subprocess.CompletedProcess([], 0, "container-id", ""),
        subprocess.CompletedProcess([], 0, "true healthy", ""),
        OSError("log collection unavailable"),
        OSError("daemon unavailable"),
    ]
    application = ContainerApplication(
        tmp_path, "local-image", tmp_path / "logs", user=(1001, 1001)
    )
    with pytest.raises(AssertionError, match="original browser failure"), application.running():
        raise AssertionError("original browser failure")
    assert "Could not collect container logs" in caplog.text
    assert "Could not remove test container" in caplog.text
    assert docker.call_args.args[0][1:3] == ["rm", "--force"]


def test_windows_retains_the_image_user(
    docker: MagicMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Avoid passing Windows' synthetic root UID to a Linux container.

    Args:
        docker: Fake Docker process boundary.
        monkeypatch: Scoped platform selection, independent of the test host.
        tmp_path: Disposable data/configuration/log directory.

    Returns:
        None: Windows startup retains the image's configured non-root identity.
    """
    monkeypatch.setattr("container_runtime.platform", "win32")
    application = ContainerApplication(tmp_path, "local-image", tmp_path / "logs")
    with application.running():
        command = docker.call_args_list[0].args[0]
        assert "--user" not in command
        assert command[-1] == "local-image"
