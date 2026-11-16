"""Build synthetic Respo batches without touching personal recipes or source PDFs."""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from factories import PNG_BYTES, RESPO_LINES, write_pdf

from przepisnik.core.database import SqliteStore
from przepisnik.core.models import VariantKind
from przepisnik.tools.aliases import VariantAliases
from przepisnik.tools.respo import RecipeCommands, RespoFolderTool, main


def source_pdf(root: Path, name: str, lines: Sequence[str] = RESPO_LINES) -> Path:
    """Write a small source PDF under an explicitly selected folder label.

    Args:
        root: Disposable source directory.
        name: Relative PDF path, including any variant folder.
        lines: Controlled recipe text for success or conflict scenarios.

    Returns:
        Path: The generated PDF.
    """
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_pdf(path, [lines], image=PNG_BYTES)


@pytest.fixture
def placeholder(tmp_path: Path) -> Path:
    """Supply a disposable fallback PNG.

    Args:
        tmp_path: Temporary filesystem root.

    Returns:
        Path: A small valid PNG.
    """
    path = tmp_path / "placeholder.png"
    path.write_bytes(PNG_BYTES)
    return path


def test_complete_batch_combines_variants_and_keeps_images(
    tmp_path: Path, placeholder: Path
) -> None:
    """Publish a complete portable bundle and retain all source bytes.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.

    Returns:
        None: One recipe with both variants and its photos passed validation.
    """
    source = tmp_path / "input"
    female = source_pdf(source, "kobieta/a.pdf")
    male = source_pdf(source, "mezczyzna/b.PDF")
    original = {path: path.read_bytes() for path in (female, male)}
    output = tmp_path / "collection"
    tool = RespoFolderTool(source, output, placeholder)
    result = tool.build(tool.discover(VariantAliases()))
    assert result["published"] is True
    assert result["integrity"] == {"recipes": 1, "variants": 2, "errors": [], "missing_images": []}
    with SqliteStore(output, read_only=True) as store:
        [recipe] = store.all()
    assert set(recipe.variants) == {VariantKind.FEMALE, VariantKind.MALE}
    assert recipe.image is not None
    assert (output / "recipes" / recipe.id / recipe.image).is_file()
    assert (output / "empty_dish.png").read_bytes() == PNG_BYTES
    assert json.loads((output / "import-report.json").read_text(encoding="utf-8")) == result
    assert (output / "USAGE.md").is_file()
    assert all(path.read_bytes() == contents for path, contents in original.items())


def test_preview_validates_without_creating_output_parent(
    tmp_path: Path, placeholder: Path
) -> None:
    """Simulate the entire collection without leaving database files in the destination.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.

    Returns:
        None: Preview reports success while the destination parent remains absent.
    """
    source = tmp_path / "input"
    source_pdf(source, "K/a.pdf")
    output = tmp_path / "new-parent/collection"
    tool = RespoFolderTool(source, output, placeholder)
    plan = tool.discover(VariantAliases(overrides=["K=female"]))
    result = tool.build(plan, dry_run=True)
    assert result["published"] is False
    assert result["dry_run"] is True
    assert not output.parent.exists()


@pytest.mark.parametrize("dry_run", [False, True])
def test_conflicts_never_publish_a_partial_collection(
    tmp_path: Path, placeholder: Path, dry_run: bool
) -> None:
    """Detect conflicts across separate PDFs in both preview and actual import.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.
        dry_run: Batch mode under test.

    Returns:
        None: A conflicting second file prevents any output publication.
    """
    source = tmp_path / "input"
    source_pdf(source, "kobieta/a.pdf")
    changed = [line.replace("Pieczemy 10 minut.", "Gotujemy 30 minut.") for line in RESPO_LINES]
    source_pdf(source, "kobieta/b.pdf", changed)
    output = tmp_path / "collection"
    tool = RespoFolderTool(source, output, placeholder)
    with pytest.raises(ValueError, match="requires review"):
        tool.build(tool.discover(VariantAliases()), dry_run=dry_run)
    assert not output.exists()
    assert not list(tmp_path.glob("respo-build-*"))


@pytest.mark.parametrize("contents", [b"broken PDF", b""])
def test_unreadable_pdfs_leave_no_collection(
    tmp_path: Path, placeholder: Path, contents: bytes
) -> None:
    """Propagate parser failures without retaining earlier successful imports.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.
        contents: Invalid PDF bytes.

    Returns:
        None: Output is absent after a parser error.
    """
    source = tmp_path / "input"
    source_pdf(source, "female/a.pdf")
    (source / "female/b.pdf").write_bytes(contents)
    tool = RespoFolderTool(source, tmp_path / "collection", placeholder)
    with pytest.raises(ValueError, match="Cannot open PDF"):
        tool.build(tool.discover(VariantAliases()))
    assert not (tmp_path / "collection").exists()


def test_pdf_without_recipes_is_rejected(tmp_path: Path, placeholder: Path) -> None:
    """Do not advertise an empty collection as a successful import.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.

    Returns:
        None: An empty extraction is a failed batch.
    """
    source = tmp_path / "input"
    source_pdf(source, "female/a.pdf", ["Not a recipe"])
    tool = RespoFolderTool(source, tmp_path / "collection", placeholder)
    with pytest.raises(ValueError, match="requires review"):
        tool.build(tool.discover(VariantAliases()))
    assert not (tmp_path / "collection").exists()


@pytest.mark.parametrize("has_existing_data", [False, True])
def test_existing_output_is_preserved(
    tmp_path: Path, placeholder: Path, has_existing_data: bool
) -> None:
    """Refuse both empty and populated destination directories.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.
        has_existing_data: Whether a user-owned sentinel is present.

    Returns:
        None: The existing destination remains unchanged.
    """
    source = tmp_path / "input"
    source.mkdir()
    output = tmp_path / "existing"
    output.mkdir()
    if has_existing_data:
        (output / "sentinel").write_text("keep", encoding="utf-8")
    before = sorted(output.iterdir())
    with pytest.raises(ValueError, match="already exists"):
        RespoFolderTool(source, output, placeholder)
    assert sorted(output.iterdir()) == before


def test_output_created_during_import_is_not_replaced(
    tmp_path: Path, placeholder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recheck the destination immediately before publishing a completed batch.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.
        monkeypatch: Scoped concurrent-creator simulation.

    Returns:
        None: The competing output and its contents are preserved.
    """
    source = tmp_path / "input"
    source_pdf(source, "female/a.pdf")
    output = tmp_path / "collection"
    original_run = RecipeCommands.run

    def create_competing_output(cli: RecipeCommands, *arguments: str) -> str:
        """Simulate a second actor creating the destination after validation.

        Args:
            cli: Validated staging CLI facade.
            arguments: Original command arguments.

        Returns:
            str: Unchanged command output.
        """
        result = original_run(cli, *arguments)
        if arguments == ("check-data",):
            output.mkdir()
            (output / "sentinel").write_text("keep", encoding="utf-8")
        return result

    monkeypatch.setattr(RecipeCommands, "run", create_competing_output)
    tool = RespoFolderTool(source, output, placeholder)
    with pytest.raises(ValueError, match="created during import"):
        tool.build(tool.discover(VariantAliases()))
    assert (output / "sentinel").read_text(encoding="utf-8") == "keep"
    assert not (output / "recipes.sqlite3").exists()


def test_folder_assignment_is_complete_before_import(tmp_path: Path, placeholder: Path) -> None:
    """Reject missing assignments and empty sources before staging.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.

    Returns:
        None: Discovery failures leave no collection.
    """
    source = tmp_path / "input"
    source.mkdir()
    tool = RespoFolderTool(source, tmp_path / "collection", placeholder)
    with pytest.raises(ValueError, match="No PDF"):
        tool.discover(VariantAliases())
    source_pdf(source, "unknown/a.pdf")
    with pytest.raises(ValueError, match="No variant"):
        tool.discover(VariantAliases())
    [item] = tool.discover(VariantAliases(), VariantKind.MALE)
    assert item.variant is VariantKind.MALE
    with pytest.raises(ValueError, match="must not be empty"):
        tool.build([])


def test_invalid_boundaries_are_rejected(tmp_path: Path, placeholder: Path) -> None:
    """Reject overlapping roots, missing input and missing bundled assets.

    Args:
        tmp_path: Temporary source/output root.
        placeholder: Valid fallback image.

    Returns:
        None: Invalid boundaries fail without filesystem writes.
    """
    source = tmp_path / "input"
    source.mkdir()
    with pytest.raises(ValueError, match="must not overlap"):
        RespoFolderTool(source, source / "output", placeholder)
    with pytest.raises(ValueError, match="Source must"):
        RespoFolderTool(tmp_path / "missing", tmp_path / "output", placeholder)
    with pytest.raises(ValueError, match="placeholder"):
        RespoFolderTool(source, tmp_path / "output", tmp_path / "missing.png")


def test_alias_configuration_and_explicit_overrides(tmp_path: Path) -> None:
    """Use explicit aliases without inferring gender from personal names.

    Args:
        tmp_path: Temporary configuration directory.

    Returns:
        None: Case folding, overrides, default labels and ambiguity were checked.
    """
    config = tmp_path / "aliases.toml"
    config.write_text('[aliases]\nAnna = "female"\nK = "male"\n', encoding="utf-8")
    aliases = VariantAliases(config, ["K=female"])
    assert aliases.resolve(["plan", "ANNA"]) is VariantKind.FEMALE
    assert aliases.resolve(["k"]) is VariantKind.FEMALE
    assert aliases.resolve(["MĘŻCZYZNA"]) is VariantKind.MALE
    assert aliases.resolve(["rodzina"]) is VariantKind.FAMILY
    with pytest.raises(ValueError, match="Contradictory"):
        aliases.resolve(["kobieta", "male"])


@pytest.mark.parametrize("alias", ["", "K", "../K=female", "a/b=female", "K=unknown", "=male"])
def test_invalid_alias_flags_are_rejected(alias: str) -> None:
    """Reject invalid paths and variant names in explicit mappings.

    Args:
        alias: Malformed CLI mapping.

    Returns:
        None: Invalid mappings do not enter a discovery plan.
    """
    with pytest.raises(ValueError):
        VariantAliases(overrides=[alias])


@pytest.mark.parametrize("contents", ['other = "value"', "[aliases]\nK = 1", "aliases = []"])
def test_invalid_alias_configuration_is_rejected(tmp_path: Path, contents: str) -> None:
    """Require the documented TOML table and string variant values.

    Args:
        tmp_path: Temporary configuration directory.
        contents: Invalid configuration contents.

    Returns:
        None: Configuration errors are explicit.
    """
    config = tmp_path / "aliases.toml"
    config.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        VariantAliases(config)


def test_cli_preview_and_errors_are_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise the agent-facing command entry point and failure summaries.

    Args:
        tmp_path: Temporary source/output root.
        capsys: Captured JSON responses.

    Returns:
        None: Successful preview and validation failure have explicit exit statuses.
    """
    source = tmp_path / "input"
    source_pdf(source, "K/a.pdf")
    arguments = ["--source", str(source), "--output", str(tmp_path / "output")]
    assert main([*arguments, "--alias", "K=female", "--dry-run"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["dry_run"] is True
    assert result["published"] is False
    assert main([*arguments, "--alias", "K=invalid"]) == 1
    failure = json.loads(capsys.readouterr().out)
    assert failure["published"] is False
    assert "error" in failure
