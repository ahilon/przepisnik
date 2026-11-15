"""Drive the command-line interface end to end on temporary data directories."""

import json
from pathlib import Path
from typing import Any

import pytest
from factories import LEGACY_RESPO_LINES, PNG_BYTES, RESPO_LINES, draft, recipe, write_pdf

from przepisnik.cli import main
from przepisnik.core.database import SqliteStore

RECIPE_ID = "ryz-z-kurczakiem"


class Cli:
    """Run the CLI against one data directory and decode its JSON output."""

    def __init__(self, data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Bind the data directory and output capture."""
        self.data_dir = data_dir
        self._capsys = capsys

    def __call__(self, *args: str, expected: int = 0) -> str:
        """Run a command, check its exit code and return standard output."""
        code = main(["--data-dir", str(self.data_dir), *args])
        captured = self._capsys.readouterr()
        assert code == expected, captured.err
        self.err = captured.err
        return captured.out

    def json(self, *args: str, expected: int = 0) -> Any:
        """Run a command and parse its JSON output."""
        return json.loads(self(*args, expected=expected))


@pytest.fixture
def cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Cli:
    """Return a CLI bound to an empty data directory."""
    return Cli(tmp_path / "data", capsys)


@pytest.fixture
def drafts(tmp_path: Path) -> Path:
    """Write an agent draft file with a photo next to it."""
    (tmp_path / "photo.png").write_bytes(PNG_BYTES)
    item = {**draft().model_dump(mode="json"), "image_file": "photo.png", "page": 4}
    path = tmp_path / "drafts.json"
    path.write_text(json.dumps([item]), encoding="utf-8")
    return path


def test_schema_command_prints_json_schemas(cli: Cli) -> None:
    """Describe drafts, recipes and metadata for agents."""
    assert cli.json("schema")["type"] == "array"
    assert "variants" in cli.json("schema", "--kind", "recipe")["properties"]
    assert "favorite" in cli.json("schema", "--kind", "metadata")["properties"]


def test_agent_drafts_are_added_and_managed(cli: Cli, drafts: Path) -> None:
    """Add drafts, then list, show, update, move and export the recipe."""
    preview = cli.json("add", str(drafts), "--variant", "female", "--dry-run")
    assert preview["counts"] == {"created": 1}
    assert cli.json("recipes", "list") == []
    report = cli.json("add", str(drafts), "--variant", "female")
    assert report["counts"] == {"created": 1}

    [listed] = cli.json("recipes", "list", "--query", "kurczak", "--variant", "female")
    assert listed["id"] == RECIPE_ID
    assert cli.json("recipes", "list", "--meal", "lunch") == []
    shown = cli.json("recipes", "show", RECIPE_ID)
    assert shown["variants"]["female"]["source"]["page"] == 4
    assert shown["image"].startswith("image-")

    assert cli.json("recipes", "favorite", RECIPE_ID, "--on")["user"]["favorite"] is True
    [favorite] = cli.json("recipes", "list", "--favorite")
    assert favorite["favorite"] is True
    patch = cli.data_dir.parent / "patch.json"
    patch.write_text(json.dumps({"tags": ["Szybkie"], "dish_types": ["main"]}), "utf-8")
    updated = cli.json("recipes", "update", RECIPE_ID, "--patch", str(patch))
    assert updated["user"]["tags"] == ["Szybkie"]
    assert len(cli.json("recipes", "list", "--dish", "main")) == 1

    copied = cli.json("variants", "copy", RECIPE_ID, "--from", "female", "--to", "family")
    assert set(copied["variants"]) == {"female", "family"}
    moved = cli.json("variants", "move", RECIPE_ID, "--from", "female", "--to", "male")
    assert set(moved["variants"]) == {"male", "family"}
    [exported] = cli.json("recipes", "export")
    assert exported["id"] == RECIPE_ID
    assert cli.json("check-data") == {
        "recipes": 1,
        "variants": 2,
        "errors": [],
        "missing_images": [],
    }


def test_add_records_url_origin(cli: Cli, drafts: Path) -> None:
    """Use the URL as the source key for web recipes."""
    cli("add", str(drafts), "--variant", "male", "--url", "https://example.com/ryz")
    with SqliteStore(cli.data_dir, read_only=True) as store:
        found = store.find("https://example.com/ryz")
    assert found is not None
    assert found.parser == "agent"


def test_check_data_reports_missing_images(cli: Cli, drafts: Path) -> None:
    """Fail the data check when a referenced photo is gone."""
    cli("add", str(drafts), "--variant", "female")
    for image in (cli.data_dir / "recipes" / RECIPE_ID).iterdir():
        image.unlink()
    result = cli.json("check-data", expected=1)
    assert result["missing_images"] == [RECIPE_ID]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "Invalid draft file"),
        (json.dumps({"title": "Bez kroków"}), "Invalid draft file"),
    ],
)
def test_invalid_drafts_are_reported_as_errors(
    cli: Cli, tmp_path: Path, content: str, message: str
) -> None:
    """Print a JSON error and exit with status 1."""
    path = tmp_path / "drafts.json"
    path.write_text(content, encoding="utf-8")
    cli("add", str(path), "--variant", "female", expected=1)
    assert message in json.loads(cli.err)["error"]


def test_missing_files_and_recipes_are_errors(cli: Cli, tmp_path: Path) -> None:
    """Report missing drafts, photos, patches and recipes without tracebacks."""
    cli("add", str(tmp_path / "missing.json"), "--variant", "female", expected=1)
    no_photo = tmp_path / "no-photo.json"
    no_photo.write_text(
        json.dumps({**draft().model_dump(mode="json"), "image_file": "missing.png"}), "utf-8"
    )
    cli("add", str(no_photo), "--variant", "female", expected=1)
    assert "Cannot read image" in cli.err
    cli("recipes", "show", "missing", expected=1)
    assert "Unknown recipe" in cli.err
    patch = tmp_path / "patch.json"
    patch.write_text("[1, 2]", "utf-8")
    cli("recipes", "update", RECIPE_ID, "--patch", str(patch), expected=1)
    assert "JSON object" in cli.err


def test_unknown_source_format_is_reported(cli: Cli, tmp_path: Path) -> None:
    """Point to the agent workflow for sources without a parser."""
    source = tmp_path / "notes.txt"
    source.write_text("Przepis", "utf-8")
    cli("detect", str(source), expected=1)
    assert "agent workflow" in cli.err


def test_respo_pdf_is_detected_dumped_and_imported(cli: Cli, tmp_path: Path) -> None:
    """Run the built-in parser on a generated Respo PDF."""
    pdf = write_pdf(tmp_path / "plan.pdf", [RESPO_LINES, LEGACY_RESPO_LINES], image=PNG_BYTES)
    assert cli.json("detect", str(pdf))["parser"] == "respo"
    dump = cli("dump-text", str(pdf), "--last-page", "1")
    assert dump.startswith("=== page 1 ===\n[image xref=")
    assert "Pinsa z sosem" in dump
    assert "=== page 2 ===" not in dump

    report = cli.json("import", str(pdf), "--variant", "female")
    assert report["counts"] == {"created": 2}
    assert report["warnings"] == []
    again = cli.json("import", str(pdf), "--variant", "female", "--parser", "respo")
    assert again["counts"] == {"unchanged": 2}
    forced = cli.json("import", str(pdf), "--variant", "female", "--force", "--enrich-meals")
    assert forced["counts"] == {"unchanged": 2}


def test_legacy_json_requires_migration(cli: Cli) -> None:
    """Refuse to work on legacy JSON until it was migrated to SQLite."""
    legacy = cli.data_dir / "recipes" / RECIPE_ID / "recipe.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(recipe().model_dump_json(), "utf-8")
    cli("recipes", "list", expected=1)
    assert "migrate-json" in cli.err
    preview = cli.json("migrate-json", "--dry-run")
    assert preview == {"created": 1, "unchanged": 0, "variants": 1, "sources": 0}
    assert cli.json("migrate-json")["created"] == 1
    assert cli.json("migrate-json")["unchanged"] == 1
    assert [item["id"] for item in cli.json("recipes", "list")] == [RECIPE_ID]
