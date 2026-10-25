"""Command-line interface; all commands print JSON (except ``dump-text``)."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import TypeAdapter, ValidationError

from przepisnik.adapters.pdf import PdfDocument
from przepisnik.core.importer import (
    ExtractedRecipe,
    ImportOptions,
    ImportReport,
    RecipeImporter,
    SourceRef,
)
from przepisnik.core.models import AGENT_PARSER, DraftItem, ImageData, VariantKind
from przepisnik.core.store import JsonRecipeStore, JsonSourceRegistry
from przepisnik.errors import DraftError, PrzepisnikError
from przepisnik.parsers.registry import default_registry

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

DATA_DIR_ENV = "PRZEPISNIK_DATA"
DEFAULT_DATA_DIR = "data"
EXIT_OK = 0
EXIT_ERROR = 1

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

    schema_cmd = commands.add_parser("schema", help="Print the JSON schema of a draft file.")
    schema_cmd.set_defaults(handler=_cmd_schema)
    return parser


def _add_merge_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--variant",
        required=True,
        choices=[kind.value for kind in VariantKind],
        help="Audience of this source: " + ", ".join(f"{k} ({k.label})" for k in VariantKind),
    )
    parser.add_argument("--replace", action="store_true", help="Overwrite differing stored data.")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")


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


def _cmd_schema(_args: argparse.Namespace) -> int:
    print(json.dumps(_DRAFTS_ADAPTER.json_schema(), indent=2, ensure_ascii=False))
    return EXIT_OK


def _run_import(
    args: argparse.Namespace, recipes: Sequence[ExtractedRecipe], origin: SourceRef
) -> ImportReport:
    importer = RecipeImporter(JsonRecipeStore(args.data_dir), JsonSourceRegistry(args.data_dir))
    options = ImportOptions(replace=args.replace, dry_run=args.dry_run)
    return importer.run(recipes, VariantKind(args.variant), origin, options)


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
