"""Run an isolated Kucharz AI session with the bundled demo collection."""

import os
import shutil
import sys
import warnings
from getpass import GetPassWarning, getpass
from pathlib import Path
from tempfile import TemporaryDirectory

from przepisnik.core.migration import migrate_json
from przepisnik.web.chef import OPENAI_API_KEY_ENV, configured_openai_key
from przepisnik.web.config import ServerConfig
from przepisnik.web.server import serve


def main() -> None:
    """Start the demo on loopback and discard the session data on exit.

    Returns:
        None: The server has stopped and its temporary collection is gone.

    Raises:
        SystemExit: A key is missing and could not be entered without echo.
    """
    if not configured_openai_key():
        try:
            with warnings.catch_warnings(action="error", category=GetPassWarning):
                key = getpass("Klucz OpenAI: ").strip()
        except (EOFError, GetPassWarning) as exc:
            raise SystemExit("Ustaw openai_api_key lub uruchom skrypt w terminalu.") from exc
        if not key:
            raise SystemExit("Nie podano klucza OpenAI.")
        os.environ[OPENAI_API_KEY_ENV] = key

    demo = Path(__file__).resolve().parents[1] / "docker" / "demo"
    config = ServerConfig()
    with TemporaryDirectory(prefix="przepisnik-chef-") as directory:
        data_dir = Path(directory).resolve(strict=True)
        shutil.copytree(demo / "recipes", data_dir / "recipes")
        shutil.copyfile(demo / "placeholder.png", data_dir / "empty_dish.png")
        migrate_json(data_dir)
        sys.stdout.write(
            f"Przepiśnik demo działa pod http://{config.host}:{config.port} (Ctrl+C)\n"
        )
        sys.stdout.flush()
        serve(data_dir, config)
    return None


if __name__ == "__main__":
    main()
