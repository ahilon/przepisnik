"""Command-line interface; all commands print JSON (except ``dump-text``)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from przepisnik.adapters.pdf import PdfDocument
from przepisnik.core.database import DATABASE_NAME, SqliteStore
from przepisnik.core.importer import (
    ExtractedRecipe,
    ImportOptions,
    ImportReport,
    RecipeImporter,
    SourceRef,
)
from przepisnik.core.migration import migrate_json
from przepisnik.core.models import (
    AGENT_PARSER,
    DishType,
    DraftItem,
    ImageData,
    MealType,
    Recipe,
    UserMetadata,
    VariantKind,
)
from przepisnik.core.recipes import RecipeFilters, select_recipes, transfer_variant, update_metadata
from przepisnik.errors import DraftError, PrzepisnikError, StoreError
from przepisnik.parsers.registry import default_registry
from przepisnik.web.server import serve

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

DATA_DIR_ENV = "PRZEPISNIK_DATA"
DEFAULT_DATA_DIR = "data"
EXIT_OK = 0
EXIT_ERROR = 1
MAX_PORT = 65535

_DRAFTS_ADAPTER = TypeAdapter(list[DraftItem])

logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    handler: Callable[[argparse.Namespace], int] = args.handler
    try:
        return handler(args)
    except PrzepisnikError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return EXIT_ERROR
    except (ValidationError, OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return EXIT_ERROR


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="przepisnik", description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get(DATA_DIR_ENV, DEFAULT_DATA_DIR)),
        help=f"Recipe database folder (env {DATA_DIR_ENV}, default ./{DEFAULT_DATA_DIR}).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    commands = parser.add_subparsers(required=True, metavar="COMMAND")

    import_cmd = commands.add_parser("import", help="Import a source with a built-in parser.")
    import_cmd.add_argument("source", type=Path)
    import_cmd.add_argument(
        "--parser",
        choices=default_registry().names,
        help="Force a parser instead of auto-detection.",
    )
    _add_merge_arguments(import_cmd)
    import_cmd.set_defaults(handler=_cmd_import)

    add_cmd = commands.add_parser("add", help="Add recipes from an agent-written draft file.")
    add_cmd.add_argument("drafts", type=Path, help="JSON file: a list of drafts (see schema).")
    origin = add_cmd.add_mutually_exclusive_group()
    origin.add_argument("--source", type=Path, help="Original source file.")
    origin.add_argument("--url", help="Original source URL.")
    _add_merge_arguments(add_cmd)
    add_cmd.set_defaults(handler=_cmd_add)

    detect_cmd = commands.add_parser("detect", help="Print which parser handles a source.")
    detect_cmd.add_argument("source", type=Path)
    detect_cmd.set_defaults(handler=_cmd_detect)

    dump_cmd = commands.add_parser("dump-text", help="Print PDF text and image placements.")
    dump_cmd.add_argument("pdf", type=Path)
    dump_cmd.add_argument("--first-page", type=int, default=1)
    dump_cmd.add_argument("--last-page", type=int, default=None)
    dump_cmd.set_defaults(handler=_cmd_dump_text)

    schema_cmd = commands.add_parser(
        "schema", help="Print a JSON schema for drafts, recipes or metadata."
    )
    schema_cmd.add_argument("--kind", choices=("draft", "recipe", "metadata"), default="draft")
    schema_cmd.set_defaults(handler=_cmd_schema)
    migrate_cmd = commands.add_parser(
        "migrate-json", help="Copy legacy JSON into SQLite, preserving originals."
    )
    migrate_cmd.add_argument("--dry-run", action="store_true")
    migrate_cmd.set_defaults(handler=_cmd_migrate)
    check_cmd = commands.add_parser(
        "check-data", help="Validate stored recipes, image references and database integrity."
    )
    check_cmd.set_defaults(handler=_cmd_check_data)
    _add_recipe_commands(commands)
    serve_cmd = commands.add_parser("serve", help="Open the local recipe browser on localhost.")
    serve_cmd.add_argument("--port", type=int, default=8000)
    serve_cmd.set_defaults(handler=_cmd_serve)
    return parser


def _cmd_serve(args: argparse.Namespace) -> int:
    if not 1 <= args.port <= MAX_PORT:
        raise StoreError("Port must be between 1 and 65535")
    if (args.data_dir / DATABASE_NAME).is_file():
        with SqliteStore(args.data_dir):
            pass
    _require_migrated(args.data_dir)
    print(f"Przepisnik: http://localhost:{args.port} (Ctrl+C to stop)", flush=True)
    serve(args.data_dir, args.port)
    return EXIT_OK


def _add_merge_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--variant",
        required=True,
        choices=[kind.value for kind in VariantKind],
        help="Audience of this source: " + ", ".join(f"{k} ({k.label})" for k in VariantKind),
    )
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
    parser.add_argument(
        "--enrich-meals",
        action="store_true",
        help="Add source meal suggestions to existing recipes; keep user overrides.",
    )


def _cmd_import(args: argparse.Namespace) -> int:
    registry = default_registry()
    parser = registry.get(args.parser) if args.parser else registry.detect(args.source)
    result = parser.parse(args.source)
    origin = SourceRef(parser=parser.name, name=args.source.name, sha256=_sha256(args.source))
    report = _run_import(args, result.recipes, origin)
    _print_report(report.model_copy(update={"warnings": result.warnings}))
    return EXIT_OK


def _cmd_add(args: argparse.Namespace) -> int:
    drafts = _load_drafts(args.drafts)
    recipes = [
        ExtractedRecipe(
            draft=draft,
            page=draft.page,
            image=_load_image(args.drafts.parent / draft.image_file) if draft.image_file else None,
        )
        for draft in drafts
    ]
    if args.url:
        origin = SourceRef(parser=AGENT_PARSER, name=args.url, url=args.url)
    else:
        source_path: Path = args.source or args.drafts
        origin = SourceRef(parser=AGENT_PARSER, name=source_path.name, sha256=_sha256(source_path))
    _print_report(_run_import(args, recipes, origin))
    return EXIT_OK


def _cmd_detect(args: argparse.Namespace) -> int:
    parser = default_registry().detect(args.source)
    print(json.dumps({"source": str(args.source), "parser": parser.name}, ensure_ascii=False))
    return EXIT_OK


def _cmd_dump_text(args: argparse.Namespace) -> int:
    with PdfDocument(args.pdf) as document:
        lines, images = document.lines(), document.images()
    last_page = args.last_page or max((line.page for line in lines), default=0)
    for page in range(args.first_page, last_page + 1):
        print(f"=== page {page} ===")
        for image in (ref for ref in images if ref.page == page):
            print(f"[image xref={image.xref} top={image.top:.0f} {image.width}x{image.height}]")
        for line in (line for line in lines if line.page == page):
            print(line.text)
    return EXIT_OK


def _cmd_schema(args: argparse.Namespace) -> int:
    schemas = {
        "draft": _DRAFTS_ADAPTER.json_schema(),
        "recipe": Recipe.model_json_schema(),
        "metadata": UserMetadata.model_json_schema(),
    }
    print(json.dumps(schemas[args.kind], indent=2, ensure_ascii=False))
    return EXIT_OK


def _cmd_check_data(args: argparse.Namespace) -> int:
    _require_migrated(args.data_dir)
    with SqliteStore(args.data_dir, read_only=True) as store:
        with store.transaction():
            errors = store.integrity_errors()
            recipes = store.all()
            missing_images = [
                recipe.id
                for recipe in recipes
                if recipe.image is not None
                and not (args.data_dir / "recipes" / recipe.id / recipe.image).is_file()
            ]
        print(
            json.dumps(
                {
                    "recipes": len(recipes),
                    "variants": sum(len(r.variants) for r in recipes),
                    "errors": errors,
                    "missing_images": missing_images,
                }
            )
        )
    return EXIT_ERROR if errors or missing_images else EXIT_OK


def _run_import(
    args: argparse.Namespace, recipes: Sequence[ExtractedRecipe], origin: SourceRef
) -> ImportReport:
    _require_migrated(args.data_dir)
    with SqliteStore(args.data_dir, read_only=args.dry_run) as store:
        importer = RecipeImporter(store, store)
        options = ImportOptions(dry_run=args.dry_run, enrich_meals=args.enrich_meals)
        return importer.run(recipes, VariantKind(args.variant), origin, options)


def _require_migrated(data_dir: Path) -> None:
    if not any((data_dir / "recipes").glob("*/recipe.json")):
        return
    if (data_dir / DATABASE_NAME).exists():
        with SqliteStore(data_dir, read_only=True) as store:
            if store.legacy_migrated():
                return
    raise StoreError(
        "Legacy JSON found; run 'przepisnik migrate-json --dry-run', "
        "then 'przepisnik migrate-json' first"
    )


def _cmd_migrate(args: argparse.Namespace) -> int:
    print(json.dumps(migrate_json(args.data_dir, dry_run=args.dry_run)))
    return EXIT_OK


def _add_recipe_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    recipes = commands.add_parser(
        "recipes", help="Browse and update recipes through validated operations."
    )
    actions = recipes.add_subparsers(required=True, metavar="ACTION")
    listing = actions.add_parser(
        "list", help="Filter recipes; lunch means obiad, dinner means kolacja."
    )
    listing.add_argument("--query", default="")
    listing.add_argument("--meal", choices=list(MealType))
    listing.add_argument("--dish", choices=list(DishType))
    listing.add_argument("--variant", choices=list(VariantKind))
    listing.add_argument("--favorite", action="store_true")
    listing.set_defaults(handler=_cmd_list)
    show = actions.add_parser("show", help="Print a complete recipe.")
    show.add_argument("id")
    show.set_defaults(handler=_cmd_show)
    favorite = actions.add_parser("favorite", help="Set or clear the favorite flag.")
    favorite.add_argument("id")
    flags = favorite.add_mutually_exclusive_group(required=True)
    flags.add_argument("--on", dest="favorite", action="store_true")
    flags.add_argument("--off", dest="favorite", action="store_false")
    favorite.set_defaults(handler=_cmd_favorite)
    update = actions.add_parser("update", help="Apply a JSON object patch to user metadata only.")
    update.add_argument("id")
    update.add_argument("--patch", type=Path, required=True)
    update.set_defaults(handler=_cmd_update)
    export = actions.add_parser(
        "export", help="Print all recipe documents as JSON (not an image backup)."
    )
    export.set_defaults(handler=_cmd_export)
    variants = commands.add_parser(
        "variants", help="Move or copy assignments without changing quantities."
    )
    transfers = variants.add_subparsers(required=True, metavar="ACTION")
    for action in ("move", "copy"):
        transfer = transfers.add_parser(action)
        transfer.add_argument("id")
        transfer.add_argument(
            "--from", dest="source_variant", choices=list(VariantKind), required=True
        )
        transfer.add_argument(
            "--to", dest="target_variant", choices=list(VariantKind), required=True
        )
        transfer.set_defaults(handler=_cmd_transfer, copy=action == "copy")


def _cmd_list(args: argparse.Namespace) -> int:
    _require_migrated(args.data_dir)
    with SqliteStore(args.data_dir, read_only=True) as store:
        recipes = select_recipes(
            store.all(),
            RecipeFilters(
                query=args.query,
                meal=MealType(args.meal) if args.meal else None,
                dish=DishType(args.dish) if args.dish else None,
                variant=VariantKind(args.variant) if args.variant else None,
                favorite=args.favorite,
            ),
        )
        print(
            json.dumps(
                [
                    {
                        "id": r.id,
                        "title": r.title,
                        "meal_types": r.effective_meal_types,
                        "dish_types": r.effective_dish_types,
                        "variants": list(r.variants),
                        "favorite": r.user.favorite,
                    }
                    for r in recipes
                ],
                ensure_ascii=False,
            )
        )
    return EXIT_OK


def _cmd_show(args: argparse.Namespace) -> int:
    _require_migrated(args.data_dir)
    with SqliteStore(args.data_dir, read_only=True) as store:
        recipe = store.get(args.id)
        if recipe is None:
            raise StoreError(f"Unknown recipe: {args.id}")
        print(recipe.model_dump_json(indent=2))
    return EXIT_OK


def _cmd_favorite(args: argparse.Namespace) -> int:
    _require_migrated(args.data_dir)
    with SqliteStore(args.data_dir) as store:
        print(
            update_metadata(store, args.id, {"favorite": args.favorite}).model_dump_json(indent=2)
        )
    return EXIT_OK


def _cmd_update(args: argparse.Namespace) -> int:
    _require_migrated(args.data_dir)
    patch = json.loads(args.patch.read_text(encoding="utf-8"))
    if not isinstance(patch, dict):
        raise DraftError("Metadata patch must be a JSON object")
    with SqliteStore(args.data_dir) as store:
        print(update_metadata(store, args.id, patch).model_dump_json(indent=2))
    return EXIT_OK


def _cmd_transfer(args: argparse.Namespace) -> int:
    _require_migrated(args.data_dir)
    with SqliteStore(args.data_dir) as store:
        recipe = transfer_variant(
            store,
            args.id,
            (VariantKind(args.source_variant), VariantKind(args.target_variant)),
            copy=args.copy,
        )
        print(recipe.model_dump_json(indent=2))
    return EXIT_OK


def _cmd_export(args: argparse.Namespace) -> int:
    _require_migrated(args.data_dir)
    with SqliteStore(args.data_dir, read_only=True) as store:
        print(
            json.dumps(
                [recipe.model_dump(mode="json") for recipe in store.all()],
                ensure_ascii=False,
                indent=2,
            )
        )
    return EXIT_OK


def _load_drafts(path: Path) -> list[DraftItem]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DraftError(f"Cannot read draft file {path}: {exc}") from exc
    try:
        data = json.loads(content)
        return _DRAFTS_ADAPTER.validate_python(data if isinstance(data, list) else [data])
    except (json.JSONDecodeError, ValidationError) as exc:
        raise DraftError(f"Invalid draft file {path}: {exc}") from exc


def _load_image(path: Path) -> ImageData:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise DraftError(f"Cannot read image {path}: {exc}") from exc
    return ImageData(content=content, extension=path.suffix.lstrip(".").lower() or "bin")


def _sha256(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    except OSError as exc:
        raise DraftError(f"Cannot read source file {path}: {exc}") from exc


def _print_report(report: ImportReport) -> None:
    print(report.model_dump_json(indent=2))
