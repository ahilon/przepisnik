"""Read-only loopback HTTP application; one SQLite connection per request."""

from __future__ import annotations

import json
import logging
import mimetypes
import sqlite3
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from przepisnik.core.database import DATABASE_NAME, SqliteStore
from przepisnik.core.models import DishType, MealType, VariantKind, slugify
from przepisnik.core.recipes import RecipeFilters, select_recipes
from przepisnik.errors import StoreError

if TYPE_CHECKING:
    from socket import socket

    from przepisnik.core.models import Recipe

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
PAGE_SIZE = 24
MAX_PAGE = 100_000


class RecipeHandler(BaseHTTPRequestHandler):
    """Serve a fixed asset allowlist and read-only recipe endpoints."""

    def __init__(
        self,
        request: socket,
        client_address: tuple[str, int],
        server: ThreadingHTTPServer,
        *,
        data_dir: Path,
    ) -> None:
        """Inject the configured data directory into each request handler."""
        self._data_dir = data_dir
        self._port = server.server_port
        super().__init__(request, client_address, server)

    def do_GET(self) -> None:
        """Dispatch reads without exposing arbitrary filesystem paths."""
        host = self.headers.get("Host", "")
        port = self._port
        if host not in {f"localhost:{port}", f"127.0.0.1:{port}"}:
            self._json({"error": "Niedozwolony adres serwera."}, HTTPStatus.FORBIDDEN)
            return
        try:
            self._dispatch()
        except (ValueError, ValidationError):
            self._json({"error": "Nieprawidłowe parametry wyszukiwania."}, HTTPStatus.BAD_REQUEST)
        except (StoreError, sqlite3.Error, OSError):
            logger.exception("Recipe browser request failed")
            self._json(
                {"error": "Nie udało się odczytać danych. Spróbuj ponownie."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _dispatch(self) -> None:
        location = urlsplit(self.path)
        assets = {"/": "index.html", "/app.css": "app.css", "/app.js": "app.js"}
        if location.path in assets:
            self._file(STATIC_DIR / assets[location.path])
            return
        with SqliteStore(self._data_dir, read_only=True) as store:
            if location.path == "/api/recipes":
                self._list(store, parse_qs(location.query))
                return
            if location.path.startswith("/api/recipes/"):
                recipe = store.get(location.path.removeprefix("/api/recipes/"))
                if recipe:
                    self._json(
                        {
                            **recipe.model_dump(mode="json"),
                            "effective_meal_types": recipe.effective_meal_types,
                            "effective_dish_types": recipe.effective_dish_types,
                            "image_url": _image_url(recipe),
                        }
                    )
                    return
            if location.path.startswith("/images/"):
                recipe = store.get(location.path.removeprefix("/images/"))
                if recipe and recipe.image:
                    image = self._data_dir / "recipes" / recipe.id / recipe.image
                    if image.is_file():
                        self._file(image)
                        return
        self._json({"error": "Nie znaleziono przepisu lub pliku."}, HTTPStatus.NOT_FOUND)

    def _list(self, store: SqliteStore, query: dict[str, list[str]]) -> None:
        values = {key: value[-1] for key, value in query.items()}
        filters = RecipeFilters(
            query=values.get("q", ""),
            meal=MealType(values["meal"]) if values.get("meal") else None,
            dish=DishType(values["dish"]) if values.get("dish") else None,
            variant=VariantKind(values["variant"]) if values.get("variant") else None,
            favorite=values.get("favorite") == "1",
            tag=values.get("tag", ""),
            uncategorized=values.get("uncategorized") == "1",
        )
        requested_page = int(values.get("page", "1"))
        if not 1 <= requested_page <= MAX_PAGE:
            raise ValueError("Invalid page")
        recipes = store.all()
        selected = sorted(
            select_recipes(recipes, filters), key=lambda recipe: slugify(recipe.title)
        )
        pages = max(1, (len(selected) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(requested_page, pages)
        visible = selected[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        self._json(
            {
                "items": [_summary(recipe) for recipe in visible],
                "total": len(selected),
                "page": page,
                "pages": pages,
                "tags": sorted({tag for recipe in recipes for tag in recipe.user.tags}),
                "counts": {
                    "all": len(recipes),
                    "favorites": sum(r.user.favorite for r in recipes),
                    "uncategorized": sum(not r.effective_meal_types for r in recipes),
                },
            }
        )

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._respond(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json", status
        )

    def _file(self, path: Path) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._respond(path.read_bytes(), content_type)

    def _respond(
        self,
        content: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header(
            "Content-Type",
            content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""),
        )
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, message: str, *args: object) -> None:
        """Send request diagnostics through application logging."""
        logger.info(message, *args)


def _image_url(recipe: Recipe) -> str | None:
    return f"/images/{recipe.id}" if recipe.image else None


def _summary(recipe: Recipe) -> dict[str, object]:
    return {
        "id": recipe.id,
        "title": recipe.title,
        "image_url": _image_url(recipe),
        "meal_types": recipe.effective_meal_types,
        "dish_types": recipe.effective_dish_types,
        "variants": list(recipe.variants),
        "favorite": recipe.user.favorite,
        "minutes": recipe.user.preparation_minutes,
        "tags": recipe.user.tags,
    }


def serve(data_dir: Path, port: int = 8000) -> None:
    """Run the local browser until interrupted; never bind a public interface."""
    if not (data_dir / DATABASE_NAME).is_file():
        raise StoreError("No SQLite database found; run migrate-json before starting the browser")
    with SqliteStore(data_dir, read_only=True) as store:
        store.all()  # Validate data before announcing a running application.
    handler = partial(RecipeHandler, data_dir=data_dir.resolve())
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Recipe browser stopped")
