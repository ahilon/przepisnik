"""Check the container API using its configured listener and allowed host."""

from __future__ import annotations

import logging
import os
from contextlib import closing
from http import HTTPStatus
from http.client import HTTPConnection, HTTPException
from pathlib import Path

from przepisnik.web.config import ServerConfig, load_server_config

logger = logging.getLogger(__name__)
DEFAULT_CONFIG = "/app/docker/server.toml"
PROBE_TIMEOUT_SECONDS = 3
RECIPE_API_PATH = "/api/recipes"
EXIT_READY = 0
EXIT_NOT_READY = 1


class ContainerHealthcheck:
    """Probe the same SQLite-backed API used by the running instance."""

    def __init__(self, configuration: ServerConfig) -> None:
        """Store the validated server settings.

        Args:
            configuration: Listener and allowed browser authorities.

        Returns:
            None: Initializes this probe.
        """
        self._configuration: ServerConfig = configuration

    @property
    def _listener_host(self) -> str:
        """Return a connectable host for the configured listener.

        Returns:
            str: Loopback for an IPv4 wildcard, otherwise the configured host.
        """
        host = self._configuration.host
        # Comparing the wildcard setting does not bind a socket to that address.
        if host == "0.0.0.0":  # noqa: S104
            return "127.0.0.1"
        return host

    def check(self) -> None:
        """Read the recipe API without depending on the external published port.

        Returns:
            None: The API returned a successful response.

        Raises:
            RuntimeError: If the API is reachable but not ready.
            OSError: If the listener cannot be reached.
            HTTPException: If the response is invalid.
        """
        authority = sorted(self._configuration.allowed_hosts)[0]
        connection = HTTPConnection(
            self._listener_host, self._configuration.port, timeout=PROBE_TIMEOUT_SECONDS
        )
        with closing(connection) as client:
            client.request("GET", RECIPE_API_PATH, headers={"Host": authority})
            response = client.getresponse()
            response.read()
            if response.status != HTTPStatus.OK:
                message = f"Recipe API returned HTTP {response.status}"
                raise RuntimeError(message)
        return None  # noqa: RET501, PLR1711 - Explicit None follows project convention.


def main() -> int:
    """Run the container health probe using the configured TOML file.

    Returns:
        int: Zero when ready; one when configuration, connection or API checks fail.
    """
    try:
        config_path = Path(os.environ.get("PRZEPISNIK_CONFIG", DEFAULT_CONFIG))
        configuration = load_server_config(config_path, required=True)
        ContainerHealthcheck(configuration).check()
    except (OSError, ValueError, HTTPException, RuntimeError) as error:
        logger.error("Container is not ready: %s", error)
        return EXIT_NOT_READY
    return EXIT_READY


if __name__ == "__main__":
    raise SystemExit(main())
