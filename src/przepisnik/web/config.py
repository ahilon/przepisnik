"""Validated network settings for a local or home-network instance."""

import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from przepisnik.constants import IPV4_LOOPBACK


class ServerConfig(BaseModel):
    """Explicit listener and browser origins; no wildcard hosts."""

    model_config = ConfigDict(extra="forbid")
    host: str = IPV4_LOOPBACK
    port: int = Field(default=8000, ge=1, le=65535)
    origins: list[str] = Field(default_factory=list)

    @field_validator("origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        """Accept only complete HTTP(S) origins without paths or credentials."""
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in value
                or parsed.netloc != parsed.netloc.lower()
                or any(character.isspace() for character in value)
            ):
                raise ValueError("Origins must be HTTP(S) URLs without paths or credentials")
            _ = parsed.port
        return values

    @property
    def allowed_origins(self) -> frozenset[str]:
        """Use loopback browser addresses when no origins were supplied."""
        return frozenset(
            self.origins or [f"http://localhost:{self.port}", f"http://{IPV4_LOOPBACK}:{self.port}"]
        )

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """Return the exact authorities accepted in the Host header."""
        return frozenset(urlsplit(origin).netloc for origin in self.allowed_origins)


def load_server_config(path: Path, *, required: bool = False) -> ServerConfig:
    """Load a TOML file, retaining loopback defaults when the default file is absent."""
    if not path.exists() and not required:
        return ServerConfig()
    with path.open("rb") as source:
        return ServerConfig.model_validate(tomllib.load(source))
