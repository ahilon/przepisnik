"""Validate network settings for the recipe browser."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from przepisnik.web.config import ServerConfig, load_server_config


def test_defaults_allow_only_loopback() -> None:
    """Listen locally and accept loopback origins for the configured port."""
    config = ServerConfig(port=8123)
    assert config.host == "127.0.0.1"
    assert config.allowed_origins == {"http://localhost:8123", "http://127.0.0.1:8123"}
    assert config.allowed_hosts == {"localhost:8123", "127.0.0.1:8123"}


def test_explicit_origins_replace_defaults() -> None:
    """Use configured HTTP(S) origins and derive Host header authorities from them."""
    config = ServerConfig(origins=["http://192.168.1.20:8000", "https://przepisy.lan"])
    assert config.allowed_origins == {"http://192.168.1.20:8000", "https://przepisy.lan"}
    assert config.allowed_hosts == {"192.168.1.20:8000", "przepisy.lan"}


@pytest.mark.parametrize(
    "origin",
    [
        "ftp://przepisy.lan",
        "http://",
        "http://user:secret@przepisy.lan",
        "http://przepisy.lan/",
        "http://przepisy.lan?x=1",
        "http://przepisy.lan#top",
        "http://*.lan",
        "http://Przepisy.lan",
        "http://przepisy.lan :8000",
        "http://przepisy.lan:99999",
    ],
)
def test_unsafe_origins_are_rejected(origin: str) -> None:
    """Refuse wildcards, credentials, paths, mixed case, spaces and invalid ports."""
    with pytest.raises(ValidationError):
        ServerConfig(origins=[origin])


@pytest.mark.parametrize("port", [0, 65536])
def test_port_must_be_valid(port: int) -> None:
    """Accept only TCP port numbers."""
    with pytest.raises(ValidationError):
        ServerConfig(port=port)


def test_missing_optional_file_uses_defaults(tmp_path: Path) -> None:
    """Fall back to defaults when the default file does not exist."""
    assert load_server_config(tmp_path / "przepisnik.toml") == ServerConfig()


def test_missing_required_file_is_an_error(tmp_path: Path) -> None:
    """Fail when an explicitly requested file is missing."""
    with pytest.raises(FileNotFoundError):
        load_server_config(tmp_path / "server.toml", required=True)


def test_toml_file_is_validated(tmp_path: Path) -> None:
    """Load values from TOML and reject unknown keys."""
    path = tmp_path / "server.toml"
    path.write_text('host = "0.0.0.0"\nport = 8001\norigins = ["http://nas:8001"]\n', "utf-8")
    assert load_server_config(path) == ServerConfig(
        host="0.0.0.0",  # noqa: S104
        port=8001,
        origins=["http://nas:8001"],
    )
    path.write_text("debug = true\n", "utf-8")
    with pytest.raises(ValidationError):
        load_server_config(path)
