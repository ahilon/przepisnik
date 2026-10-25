# przepisnik

Recipe knowledge base built from diet-plan PDFs, recipe websites and own recipes.
Every source is normalised to one JSON schema, ready to be rendered with templates.

## Setup

```bash
uv sync
```

The agent skill lives in `.agents/skills/przepisnik` (read by Codex). Link it for
Claude Code once per clone:

```powershell
# Windows
New-Item -ItemType Junction -Path .claude\skills\przepisnik -Target "$PWD\.agents\skills\przepisnik"
```

```bash
# macOS / Linux
mkdir -p .claude/skills && ln -s ../../.agents/skills/przepisnik .claude/skills/przepisnik
```

## Usage

```bash
uv run przepisnik detect "przepisy/Dieta (1).pdf"                 # which parser handles it
uv run przepisnik import "przepisy/Dieta (1).pdf" --variant female --dry-run
uv run przepisnik import "przepisy/Dieta (1).pdf" --variant female
uv run przepisnik schema                                        # draft format for agents
uv run przepisnik add drafts.json --variant family --url https://example.com/recipe
uv run przepisnik dump-text some.pdf --first-page 1 --last-page 2
```

Variants: `male` (Mężczyzna), `female` (Kobieta), `family` (Rodzina).
The database location defaults to `./data` (override with `--data-dir` or `PRZEPISNIK_DATA`).

## Data layout

```
data/recipes/<recipe-id>/recipe.json   # schema: src/przepisnik/core/models.py (Recipe)
data/recipes/<recipe-id>/image.png
data/sources.json                      # imported sources (by file hash or URL)
```

- Steps live on the recipe; a variant has its own `steps` only when they differ.
- Recipes sharing a title but with different ingredients are stored as versions
  (`<id>`, `<id>-2`, ...).
- Nutrition and ingredients are per `servings` of the variant (Respo: always 1);
  `suggested_batch_portions` tells how many portions to cook at once.

## Architecture

- `core/` - shared library: schema, merging (variants, versions, conflicts), JSON store.
  Every source reaches the store through `core.importer.RecipeImporter`.
- `parsers/` - code parsers for frequent, stable formats (`respo`), auto-detected via
  `parsers/registry.py`. Other sources are extracted by the agent skill
  (`.agents/skills/przepisnik`) and added with `przepisnik add`.
- `adapters/` - file format readers (PDF via PyMuPDF).

## Development

```bash
uv run ruff format . && uv run ruff check . && uv run python -m mypy src
```
