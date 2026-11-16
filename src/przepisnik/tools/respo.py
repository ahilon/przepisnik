"""Build a portable Respo collection through the existing validated recipe CLI."""

import argparse
import json
import shutil
import tempfile
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from przepisnik.cli import main as recipe_main
from przepisnik.core.importer import ImportReport
from przepisnik.core.models import VariantKind
from przepisnik.tools.aliases import VariantAliases

REPORT_NAME = "import-report.json"
USAGE_NAME = "USAGE.md"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1


@dataclass(frozen=True)
class ImportSource:
    """One source PDF and its explicitly resolved portion variant."""

    path: Path
    relative_name: str
    variant: VariantKind


class RecipeCommands:
    """Invoke the public recipe CLI against a disposable staging directory."""

    def __init__(self, data_dir: Path) -> None:
        """Bind commands to one temporary collection.

        Args:
            data_dir: Staging directory, never an existing user database.

        Returns:
            None: Stores the target for validated CLI calls.
        """
        self._data_dir = data_dir
        return None

    def run(self, *arguments: str) -> str:
        """Capture structured CLI output and fail on unsuccessful commands.

        Args:
            arguments: Arguments following the global data-directory option.

        Returns:
            str: The command's JSON response.

        Raises:
            ValueError: If the validated CLI rejects the operation.
        """
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = recipe_main(["--data-dir", str(self._data_dir), *arguments])
        if status != EXIT_SUCCESS:
            raise ValueError(errors.getvalue().strip() or output.getvalue().strip())
        return output.getvalue()


class RespoFolderTool:
    """Prepare a fresh, validated collection without overwriting existing data."""

    def __init__(self, source: Path, output: Path, placeholder: Path) -> None:
        """Validate source/output boundaries before any temporary import.

        Args:
            source: Root folder containing Respo PDFs and variant folders.
            output: New directory for SQLite, images, usage and import report.
            placeholder: Versioned fallback image bundled with this repository.

        Returns:
            None: Stores validated paths.

        Raises:
            ValueError: If paths overlap, input is missing or output already exists.
        """
        self._source = source.resolve()
        self._output = output.resolve()
        self._placeholder = placeholder
        if source.is_symlink() or not self._source.is_dir():
            raise ValueError("Source must be an existing directory")
        if output.is_symlink() or self._output.exists():
            raise ValueError("Output already exists; choose a new directory")
        if self._source.is_relative_to(self._output) or self._output.is_relative_to(self._source):
            raise ValueError("Source and output directories must not overlap")
        if not placeholder.is_file():
            raise ValueError("The repository placeholder image is missing")
        self._reports: list[ImportReport] = []
        return None

    def discover(
        self, aliases: VariantAliases, fallback: VariantKind | None = None
    ) -> list[ImportSource]:
        """Enumerate sorted PDFs and resolve every variant before importing any file.

        Args:
            aliases: Explicit directory mappings.
            fallback: Optional variant for otherwise unassigned PDFs.

        Returns:
            list[ImportSource]: A deterministic, completely assigned import plan.

        Raises:
            ValueError: If no PDFs exist, a symlink occurs or assignment is invalid.
        """
        sources: list[ImportSource] = []
        for path in sorted(self._source.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Source symlinks are not supported: {path}")
            if not path.is_file() or path.suffix.casefold() != ".pdf":
                continue
            relative = path.relative_to(self._source)
            labels = [self._source.name, *relative.parts[:-1]]
            variant = aliases.resolve(labels, fallback)
            sources.append(ImportSource(path, relative.as_posix(), variant))
        if not sources:
            raise ValueError("No PDF files found in the source directory")
        return sources

    def build(self, sources: Sequence[ImportSource], *, dry_run: bool = False) -> dict[str, object]:
        """Simulate or publish a complete batch using a disposable SQLite collection.

        Args:
            sources: Fully assigned input plan from discover.
            dry_run: Build in temporary storage and discard all generated data.

        Returns:
            dict[str, object]: Per-file results, output path and publication state.

        Raises:
            ValueError: If imports conflict, produce no recipes or fail validation.
            OSError: If filesystem operations fail.
        """
        self._reports = []
        if not sources:
            raise ValueError("An import plan must not be empty")
        if self._output.exists():
            raise ValueError("Output already exists; choose a new directory")
        parent: Path | None = None
        if not dry_run:
            self._output.parent.mkdir(parents=True, exist_ok=True)
            parent = self._output.parent
        with tempfile.TemporaryDirectory(prefix="respo-build-", dir=parent) as temporary:
            data_dir = Path(temporary) / "collection"
            cli = RecipeCommands(data_dir)
            cli.run("migrate-json")
            for source in sources:
                report = ImportReport.model_validate_json(
                    cli.run(
                        "import",
                        str(source.path),
                        "--parser",
                        "respo",
                        "--variant",
                        source.variant.value,
                    )
                )
                self._reports.append(report)
                if report.conflicts or not sum(report.counts.values()):
                    raise ValueError(f"Import requires review: {source.relative_name}")
            integrity = json.loads(cli.run("check-data"))
            shutil.copyfile(self._placeholder, data_dir / "empty_dish.png")
            result = self.summary(sources, dry_run=dry_run)
            result["integrity"] = integrity
            (data_dir / REPORT_NAME).write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (data_dir / USAGE_NAME).write_text(self._usage(), encoding="utf-8")
            if not dry_run:
                if self._output.exists():
                    raise ValueError("Output was created during import; refusing to replace it")
                data_dir.rename(self._output)
        return result

    def summary(self, sources: Sequence[ImportSource], *, dry_run: bool) -> dict[str, object]:
        """Describe completed imports without exposing the temporary database path.

        Args:
            sources: Planned source paths and variant assignments.
            dry_run: Whether this batch is a discarded preview.

        Returns:
            dict[str, object]: JSON-compatible summary, including any completed reports.
        """
        return {
            "dry_run": dry_run,
            "published": not dry_run,
            "output": str(self._output),
            "sources": [
                {"file": item.relative_name, "variant": item.variant.value} for item in sources
            ],
            "imports": [
                report.model_dump(mode="json", exclude={"dry_run"}) for report in self._reports
            ],
        }

    def _usage(self) -> str:
        """Explain portable output and the existing application commands.

        Returns:
            str: A short Markdown guide shipped alongside generated data.
        """
        return (
            "# Imported Respo collection\n\n"
            "Keep this entire directory: recipes.sqlite3, recipes/ photos and empty_dish.png.\n"
            "Run from a Przepisnik checkout with `uv sync --locked` completed.\n\n"
            "```sh\n"
            'uv run przepisnik --data-dir "<collection-directory>" check-data\n'
            'uv run przepisnik --data-dir "<collection-directory>" serve\n'
            "```\n\nOpen http://localhost:8000. Replace the placeholder path with this directory.\n"
            "For Docker, mount the entire collection at /data and configure writable access\n"
            "for the image user (UID/GID 10001); see docker/README.md. Keep your own backups.\n"
        )


def main(argv: Sequence[str] | None = None, *, project_root: Path | None = None) -> int:
    """Run the standalone folder tool with explicit source and output paths.

    Args:
        argv: Optional command-line arguments, otherwise read from the process.
        project_root: Repository root for the bundled placeholder image.

    Returns:
        int: Zero for a complete preview/import; one for a rejected batch.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--variant", choices=list(VariantKind))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    tool: RespoFolderTool | None = None
    sources: list[ImportSource] = []
    try:
        aliases = VariantAliases(args.config, args.alias)
        root = project_root or Path.cwd()
        tool = RespoFolderTool(args.source, args.output, root / "docker/demo/placeholder.png")
        fallback = VariantKind(args.variant) if args.variant else None
        sources = tool.discover(aliases, fallback)
        result = tool.build(sources, dry_run=args.dry_run)
    except (ValueError, OSError) as error:
        result = tool.summary(sources, dry_run=args.dry_run) if tool else {}
        result.update(error=str(error), published=False)
        print(json.dumps(result, ensure_ascii=False))
        return EXIT_FAILURE
    print(json.dumps(result, ensure_ascii=False))
    return EXIT_SUCCESS
