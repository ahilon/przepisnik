"""Isolated data and HTTP server fixtures for browser tests."""

import shutil
from collections.abc import Iterator
from contextlib import closing
from functools import partial
from http import HTTPStatus
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from container_runtime import ContainerApplication
from playwright.sync_api import Page

from przepisnik.core.migration import migrate_json
from przepisnik.web.config import ServerConfig
from przepisnik.web.server import RecipeHandler


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the explicit opt-in to an already built container image.

    Args:
        parser: Pytest's command-line option registry.

    Returns:
        None: Registers the container backend option.
    """
    parser.addoption(
        "--container-image",
        help="Run isolated application containers from this already built Linux image",
    )


@pytest.fixture(scope="session")
def base_url(pytestconfig: pytest.Config) -> str | None:
    """Replace pytest-playwright's deprecated instance-method URL fallback."""
    value = pytestconfig.getoption("base_url") or pytestconfig.getini("base_url")
    return str(value) if value else None


@pytest.fixture
def recipe_data(tmp_path: Path) -> Path:
    """Create a fresh database and photo collection from versioned demo fixtures."""
    fixtures = Path(__file__).resolve().parents[1] / "docker" / "demo"
    data_dir = tmp_path / "data"
    shutil.copytree(fixtures / "recipes", data_dir / "recipes")
    shutil.copyfile(fixtures / "placeholder.png", data_dir / "empty_dish.png")
    migrate_json(data_dir)
    return data_dir


@pytest.fixture
def app_url(recipe_data: Path, pytestconfig: pytest.Config) -> Iterator[str]:
    """Serve disposable data using the explicitly selected backend.

    Args:
        recipe_data: This test's isolated SQLite database and photos.
        pytestconfig: Settings including the optional prebuilt container image.

    Yields:
        str: URL of the healthy application instance.
    """
    image = pytestconfig.getoption("--container-image")
    if image:
        artifacts_dir = Path(str(pytestconfig.getoption("--output"))) / "container-logs"
        application = ContainerApplication(recipe_data, str(image), artifacts_dir)
        with application.running() as url:
            yield url
        return
    handler = partial(RecipeHandler, data_dir=recipe_data, config=ServerConfig())
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        config = ServerConfig(port=server.server_port)
        server.RequestHandlerClass = partial(RecipeHandler, data_dir=recipe_data, config=config)
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=5)) as client:
                client.request("GET", "/api/recipes")
                response = client.getresponse()
                response.read()
                if response.status != HTTPStatus.OK:
                    raise RuntimeError("Test application did not become ready")
            yield url
        finally:
            server.shutdown()
            thread.join()


@pytest.fixture
def app_page(page: Page, app_url: str) -> Page:
    """Open the isolated application using a fresh Playwright page."""
    page.goto(app_url)
    return page
