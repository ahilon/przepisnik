"""Configurable recipe editor; one SQLite connection per request."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import secrets
import sqlite3
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from przepisnik.core.combined import COMBINED_VARIANT, CombinedVariantBuilder
from przepisnik.core.database import DATABASE_NAME, SqliteStore
from przepisnik.core.models import (
    DishType,
    ImageData,
    MealType,
    Recipe,
    Source,
    VariantKind,
    slugify,
)
from przepisnik.core.recipes import RecipeFilters, select_recipes
from przepisnik.core.shared_variants import (
    SHARED_SOURCES_STATE_PREFIX,
    SharedVariantMerger,
    VariantMergeConflictError,
)
from przepisnik.core.shopping import (
    ShoppingConflictError,
    ShoppingList,
    load_shopping_list,
    save_shopping_list,
)
from przepisnik.errors import StoreError
from przepisnik.web.config import ServerConfig
from przepisnik.web.nutrition_ai import (
    MAX_ESTIMATE_BYTES,
    NutritionEstimateError,
    NutritionEstimateRequest,
    NutritionEstimator,
    OpenAINutritionEstimator,
)

if TYPE_CHECKING:
    from socket import socket


logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
PAGE_SIZE = 24
MAX_PAGE = 100_000
MAX_BODY_BYTES = 12_000_000
MAX_IMAGE_BYTES = 8_000_000
NUTRITION_ESTIMATE_PATH = "/api/nutrition/estimate"
API_KEY_ENV = "api_key"


class RecipeServer(ThreadingHTTPServer):
    """Keep the configured estimator scoped to a single server instance."""

    nutrition_estimator: NutritionEstimator | None = None


class RecipeHandler(BaseHTTPRequestHandler):
    """Serve a fixed asset allowlist and validated recipe endpoints."""

    def __init__(
        self,
        request: socket,
        client_address: tuple[str, int],
        server: ThreadingHTTPServer,
        *,
        data_dir: Path,
        config: ServerConfig,
    ) -> None:
        """Set up the handler with its storage, network settings and optional estimator.

        Args:
            request: Client connection.
            client_address: Client host and port.
            server: Server handling the connection.
            data_dir: Directory containing recipes and their images.
            config: Allowed listener addresses and origins.
        """
        self._data_dir = data_dir
        self._config = config
        self._nutrition_estimator = (
            server.nutrition_estimator if isinstance(server, RecipeServer) else None
        )
        super().__init__(request, client_address, server)

    def do_GET(self) -> None:
        """Dispatch reads without exposing arbitrary filesystem paths."""
        host = self.headers.get("Host", "")
        if host not in self._config.allowed_hosts:
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
        assets = {
            "/": "index.html",
            "/app.css": "app.css",
            "/app.js": "app.js",
            "/shopping.js": "shopping.js",
        }
        if location.path in assets:
            self._file(STATIC_DIR / assets[location.path])
            return
        if location.path == "/api/version":
            self._json({"version": version("przepisnik")})
            return
        if location.path == "/empty_dish.png":
            self._file(self._data_dir / "empty_dish.png")
            return
        self._read_data(location.path, parse_qs(location.query))

    def _read_data(self, path: str, query: dict[str, list[str]]) -> None:
        """Read validated application data and derived recipe capabilities.

        Args:
            path: Parsed request path.
            query: Parsed query parameters for collection filtering.

        Returns:
            None: Writes the requested data or a not-found response.
        """
        with SqliteStore(self._data_dir, read_only=True) as store:
            if path == "/api/shopping-list":
                self._json(load_shopping_list(store).model_dump(mode="json"))
                return
            if path == "/api/recipes":
                self._list(store, query)
                return
            if path.startswith("/api/recipes/"):
                recipe = store.get(path.removeprefix("/api/recipes/"))
                if recipe:
                    combined = CombinedVariantBuilder().build(recipe)
                    self._json(
                        {
                            **recipe.model_dump(mode="json"),
                            "effective_meal_types": recipe.effective_meal_types,
                            "effective_dish_types": recipe.effective_dish_types,
                            "image_url": _image_url(recipe),
                            "combined_variant": combined.model_dump(mode="json")
                            if combined
                            else None,
                            "can_merge_variants": SharedVariantMerger().can_merge(recipe),
                            "nutrition_ai_available": self._nutrition_estimator is not None,
                            "shared_sources": [
                                source.model_dump(mode="json")
                                for source in self._shared_sources(store, recipe)
                            ],
                        }
                    )
                    return
            if path.startswith("/images/"):
                recipe = store.get(path.removeprefix("/images/"))
                if recipe and recipe.image:
                    image = self._data_dir / "recipes" / recipe.id / recipe.image
                    if image.is_file():
                        self._file(image)
                        return
        self._json({"error": "Nie znaleziono przepisu lub pliku."}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        """Validate and dispatch same-origin JSON requests.

        Returns:
            None: Writes a success response or an appropriate validation error.
        """
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host not in self._config.allowed_hosts or (
            origin is not None
            and (origin not in self._config.allowed_origins or urlsplit(origin).netloc != host)
        ):
            self._json({"error": "Niedozwolone źródło zapisu."}, HTTPStatus.FORBIDDEN)
            return
        if self.headers.get_content_type() != "application/json":
            self._json({"error": "Wymagany format JSON."}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        try:
            path = urlsplit(self.path).path
            estimating = path == NUTRITION_ESTIMATE_PATH
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= (MAX_ESTIMATE_BYTES if estimating else MAX_BODY_BYTES):
                message = (
                    "Lista składników przekracza limit żądania."
                    if estimating
                    else "Formularz przekracza limit 12 MB."
                )
                self._json(
                    {"error": message},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Invalid payload")
            self._write_payload(payload)
        except ShoppingConflictError:
            self._json(
                {
                    "error": "Lista zmieniła się na innym urządzeniu. "
                    "Wczytano aktualną wersję — spróbuj ponownie."
                },
                HTTPStatus.CONFLICT,
            )
        except VariantMergeConflictError:
            self._json(
                {"error": "Nie można złączyć wariantów — ich dane się różnią. Odśwież przepis."},
                HTTPStatus.CONFLICT,
            )
        except (ValueError, KeyError, TypeError):
            if urlsplit(self.path).path == "/api/shopping-list":
                self._json(
                    {"error": "Sprawdź nazwy produktów, ilości i jednostki na liście."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            self._json(
                {"error": "Sprawdź formularz i zdjęcie. Wymagane: nazwa, składniki i kroki."},
                HTTPStatus.BAD_REQUEST,
            )
        except (StoreError, sqlite3.Error, OSError):
            logger.exception("Recipe save failed")
            self._json(
                {"error": "Nie udało się zapisać przepisu. Spróbuj ponownie."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _write_payload(self, payload: dict[str, object]) -> None:
        """Dispatch validated JSON to the requested operation.

        Args:
            payload: Decoded JSON object from a same-origin request.

        Returns:
            None: Writes the operation's response.
        """
        path = urlsplit(self.path).path
        if path == NUTRITION_ESTIMATE_PATH:
            self._estimate_nutrition(payload)
            return None
        if path.startswith("/api/recipes/") and path.endswith("/merge-variants"):
            recipe_id = path.removeprefix("/api/recipes/").removesuffix("/merge-variants")
            self._merge_variants(recipe_id, payload)
            return None
        if path == "/api/shopping-list":
            proposed = ShoppingList.model_validate(payload)
            with SqliteStore(self._data_dir) as store, store.transaction():
                shopping = save_shopping_list(store, proposed)
            self._json(shopping.model_dump(mode="json"))
            return
        creating = path == "/api/recipes"
        if not creating and not path.startswith("/api/recipes/"):
            self._json({"error": "Nie znaleziono adresu."}, HTTPStatus.NOT_FOUND)
            return
        image = _uploaded_image(payload.get("upload"))
        with SqliteStore(self._data_dir) as store, store.transaction():
            current = None if creating else store.get(path.removeprefix("/api/recipes/"))
            if not creating and current is None:
                self._json({"error": "Nie znaleziono przepisu."}, HTTPStatus.NOT_FOUND)
                return
            if (
                current
                and payload.get("updated_at") != current.model_dump(mode="json")["updated_at"]
            ):
                self._json(
                    {"error": "Przepis zmienił się. Otwórz go ponownie przed edycją."},
                    HTTPStatus.CONFLICT,
                )
                return
            fields = payload["recipe"]
            if not isinstance(fields, dict) or fields.keys() - {
                "title",
                "steps",
                "variants",
                "user",
                "notes",
            }:
                raise ValueError("Unexpected fields")
            original = current.model_dump() if current else {}
            identity = current.id if current else f"recipe-{secrets.token_hex(8)}"
            recipe = Recipe.model_validate({**original, **fields, "id": identity})
            saved = store.save(recipe, image)
        self._json(
            {"id": saved.id, "changed": current is None or saved.updated_at != current.updated_at},
            HTTPStatus.CREATED if creating else HTTPStatus.OK,
        )

    def _estimate_nutrition(self, payload: dict[str, object]) -> None:
        """Return a draft estimate without opening the recipe store.

        Args:
            payload: Ingredient quantities and servings from the editor.

        Returns:
            None: Writes an estimate or a user-facing error.
        """
        if self._nutrition_estimator is None:
            self._json(
                {"error": f"Szacowanie AI wymaga ustawienia {API_KEY_ENV} na serwerze."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return None
        try:
            request = NutritionEstimateRequest.model_validate(payload)
        except ValidationError:
            self._json(
                {"error": "Sprawdź składniki, ich ilości i liczbę porcji."},
                HTTPStatus.BAD_REQUEST,
            )
            return None
        try:
            nutrition = self._nutrition_estimator.estimate(request)
        except NutritionEstimateError:
            self._json(
                {"error": "Nie udało się oszacować wartości odżywczych. Spróbuj ponownie."},
                HTTPStatus.BAD_GATEWAY,
            )
            return None
        self._json(nutrition.model_dump(mode="json"))
        return None

    def _merge_variants(self, recipe_id: str, payload: dict[str, object]) -> None:
        """Collapse current matching variants and preserve all source references atomically.

        Args:
            recipe_id: Stable identity of the recipe being merged.
            payload: The exact updated_at token observed by the browser.

        Returns:
            None: Writes the saved identity, or a missing/stale recipe response.

        Raises:
            ValueError: If the request contains unexpected fields.
            VariantMergeConflictError: If current variant content is incompatible.
        """
        if payload.keys() != {"updated_at"}:
            raise ValueError("Variant merge requires only an updated_at token")
        with SqliteStore(self._data_dir) as store, store.transaction():
            current = store.get(recipe_id)
            if current is None:
                self._json({"error": "Nie znaleziono przepisu."}, HTTPStatus.NOT_FOUND)
                return None
            if payload["updated_at"] != current.model_dump(mode="json")["updated_at"]:
                self._json(
                    {"error": "Przepis zmienił się. Odśwież go przed łączeniem wariantów."},
                    HTTPStatus.CONFLICT,
                )
                return None
            merged = SharedVariantMerger().merge(current)
            sources = self._shared_sources(store, current)
            for variant in current.variants.values():
                if variant.source is not None and variant.source not in sources:
                    sources.append(variant.source)
            saved = store.save(merged)
            store.set_state(
                f"{SHARED_SOURCES_STATE_PREFIX}{current.id}",
                json.dumps([source.model_dump(mode="json") for source in sources]),
            )
        self._json({"id": saved.id, "changed": True})
        return None

    @staticmethod
    def _shared_sources(store: SqliteStore, recipe: Recipe) -> list[Source]:
        """Load source references retained when audience variants were collapsed.

        Args:
            store: Current recipe database connection.
            recipe: Recipe whose shared variant and retained sources are requested.

        Returns:
            list[Source]: Unique shared provenance, including the active variant's source.
        """
        stored = store.get_state(f"{SHARED_SOURCES_STATE_PREFIX}{recipe.id}")
        sources = [Source.model_validate(value) for value in json.loads(stored or "[]")]
        shared = recipe.variants.get(VariantKind.FAMILY)
        if shared is not None and shared.source is not None and shared.source not in sources:
            sources.append(shared.source)
        return sources

    def _list(self, store: SqliteStore, query: dict[str, list[str]]) -> None:
        values = {key: value[-1] for key, value in query.items()}
        filters = RecipeFilters(
            query=values.get("q", ""),
            meal=MealType(values["meal"]) if values.get("meal") else None,
            dish=DishType(values["dish"]) if values.get("dish") else None,
            variant=VariantKind(values["variant"])
            if values.get("variant") and values["variant"] != COMBINED_VARIANT
            else None,
            favorite=values.get("favorite") == "1",
            tag=values.get("tag", ""),
            uncategorized=values.get("uncategorized") == "1",
            hidden=values.get("hidden") == "1",
        )
        requested_page = int(values.get("page", "1"))
        if not 1 <= requested_page <= MAX_PAGE:
            raise ValueError("Invalid page")
        recipes = store.all()
        active = [recipe for recipe in recipes if not recipe.user.hidden]
        collection = [recipe for recipe in recipes if recipe.user.hidden == filters.hidden]
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
                "tags": sorted({tag for recipe in collection for tag in recipe.user.tags}),
                "counts": {
                    "all": len(active),
                    "favorites": sum(r.user.favorite for r in active),
                    "uncategorized": sum(not r.effective_meal_types for r in active),
                    "hidden": len(recipes) - len(active),
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
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, message: str, *args: object) -> None:
        """Send request diagnostics through application logging."""
        logger.info(message, *args)


def _uploaded_image(value: object) -> ImageData | None:
    """Decode a bounded raster upload without trusting a supplied file name."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid image")
    content = base64.b64decode(value, validate=True)
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 8 MB")
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif content.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    elif content[:6] in {b"GIF87a", b"GIF89a"}:
        extension = "gif"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        extension = "webp"
    else:
        raise ValueError("Unsupported raster image")
    return ImageData(content=content, extension=extension)


def _image_url(recipe: Recipe) -> str:
    return f"/images/{recipe.id}" if recipe.image else "/empty_dish.png"


def _summary(recipe: Recipe) -> dict[str, object]:
    return {
        "id": recipe.id,
        "title": recipe.title,
        "image_url": _image_url(recipe),
        "meal_types": recipe.effective_meal_types,
        "dish_types": recipe.effective_dish_types,
        "variants": list(recipe.variants),
        "favorite": recipe.user.favorite,
        "hidden": recipe.user.hidden,
        "minutes": recipe.user.preparation_minutes,
        "tags": recipe.user.tags,
    }


def serve(data_dir: Path, config: ServerConfig) -> None:
    """Run the web server with instance network settings and optional nutrition AI.

    Args:
        data_dir: Directory containing the validated instance database and images.
        config: Listener configuration and allowed browser origins.

    Returns:
        None: Runs until the server is stopped.
    """
    if not (data_dir / DATABASE_NAME).is_file():
        raise StoreError("No SQLite database found; run migrate-json before starting the browser")
    with SqliteStore(data_dir) as store:
        store.all()  # Validate data before announcing a running application.
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    handler = partial(RecipeHandler, data_dir=data_dir.resolve(), config=config)
    with RecipeServer((config.host, config.port), handler) as server:
        server.nutrition_estimator = OpenAINutritionEstimator(api_key) if api_key else None
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Recipe browser stopped")
