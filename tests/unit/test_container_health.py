"""Regression tests for the image's configured HTTP readiness probe."""

from http.client import HTTPException
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from przepisnik.web import health
from przepisnik.web.config import ServerConfig


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace network transport while retaining request and teardown assertions.

    Args:
        monkeypatch: Scoped replacement of the HTTP connection factory.

    Returns:
        MagicMock: Factory returning a successful API connection by default.
    """
    factory = MagicMock()
    factory.return_value.getresponse.return_value.status = 200
    monkeypatch.setattr(health, "HTTPConnection", factory)
    return factory


@pytest.mark.parametrize("host", ["0.0.0.0", "127.0.0.1"])  # noqa: S104 - Listener test data.
def test_probe_uses_internal_listener_and_external_allowed_host(
    connection: MagicMock, host: str
) -> None:
    """Connect internally while honoring a browser authority with a different port.

    Args:
        connection: Mock transport factory, without a real network listener.
        host: Supported container wildcard or loopback listener address.

    Returns:
        None: The correct listener, Host header and cleanup were asserted.
    """
    configuration = ServerConfig(host=host, port=8123, origins=["http://recipes.invalid:4567"])
    health.ContainerHealthcheck(configuration).check()
    connection.assert_called_once_with("127.0.0.1", 8123, timeout=3)
    client = connection.return_value
    client.request.assert_called_once_with(
        "GET", "/api/recipes", headers={"Host": "recipes.invalid:4567"}
    )
    client.getresponse.return_value.read.assert_called_once_with()
    client.close.assert_called_once_with()


def test_non_success_response_is_unhealthy_and_closes_connection(connection: MagicMock) -> None:
    """Reject an available listener whose recipe API cannot serve requests.

    Args:
        connection: Mock transport returning an unavailable API response.

    Returns:
        None: An unsuccessful response fails readiness and closes the socket.
    """
    connection.return_value.getresponse.return_value.status = 503
    with pytest.raises(RuntimeError, match="HTTP 503"):
        health.ContainerHealthcheck(ServerConfig()).check()
    connection.return_value.close.assert_called_once_with()


@pytest.mark.parametrize("error", [ConnectionRefusedError("offline"), HTTPException("bad HTTP")])
def test_transport_failure_is_unhealthy(
    connection: MagicMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception
) -> None:
    """Convert socket and protocol errors into the health command's failing exit status.

    Args:
        connection: Transport factory that fails during an API request.
        monkeypatch: Scoped environment replacement for the configuration path.
        tmp_path: Disposable configuration directory.
        error: Representative socket or protocol error.

    Returns:
        None: Failure is reported as a nonzero exit code and the socket is closed.
    """
    configuration = tmp_path / "server.toml"
    configuration.write_text("port = 8123\n", encoding="utf-8")
    monkeypatch.setenv("PRZEPISNIK_CONFIG", str(configuration))
    connection.return_value.request.side_effect = error
    assert health.main() == 1
    connection.return_value.close.assert_called_once_with()


@pytest.mark.parametrize("contents", [None, "port = [", "port = 0\n"])
def test_missing_or_invalid_configuration_never_reports_ready(
    connection: MagicMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, contents: str | None
) -> None:
    """Require a readable, syntactically and semantically valid configuration.

    Args:
        connection: Mock transport that must not be contacted.
        monkeypatch: Scoped configuration-path override.
        tmp_path: Disposable configuration directory.
        contents: Missing, malformed or invalid TOML fixture.

    Returns:
        None: Invalid settings fail before attempting an API request.
    """
    configuration = tmp_path / "server.toml"
    if contents is not None:
        configuration.write_text(contents, encoding="utf-8")
    monkeypatch.setenv("PRZEPISNIK_CONFIG", str(configuration))
    assert health.main() == 1
    connection.assert_not_called()


def test_command_loads_custom_configuration_and_reports_ready(
    connection: MagicMock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exercise successful configuration loading through the command entry point.

    Args:
        connection: Successful API transport factory.
        monkeypatch: Scoped configuration-path override.
        tmp_path: Disposable configuration directory.

    Returns:
        None: The command succeeds using the supplied listener port.
    """
    configuration = tmp_path / "server.toml"
    configuration.write_text("port = 8123\n", encoding="utf-8")
    monkeypatch.setenv("PRZEPISNIK_CONFIG", str(configuration))
    assert health.main() == 0
    connection.assert_called_once_with("127.0.0.1", 8123, timeout=3)
