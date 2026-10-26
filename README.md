# przepisnik

Recipe knowledge base built from diet-plan PDFs, recipe websites and own recipes.
Every source is validated against a shared Pydantic schema and stored in SQLite.
The CLI, project skills and local recipe browser share the same application operations.

## Version status

The current work targets **1.3.0**: a local recipe browser with photo cards,
search, filters, pagination and recipe details with variant switching.
Version **1.2.0** introduced validation and import safeguards; **1.1.0** introduced
SQLite and recipe management. See [CHANGELOG.md](CHANGELOG.md) for the short history.
Version 1.3.0 is not released; package metadata still declares 1.2.0.
Package versions are independent of recipe document and SQLite schema versions.

SQLite schema upgrades run automatically when opening a database for writing,
including server startup. Existing databases get a `.before-vN.bak` SQLite backup
before an upgrade. All pending steps run in one transaction; a failure rolls back
both schema changes and the version. Read-only commands require an up-to-date
schema; start the server once to upgrade an older database. Newer unsupported
versions are rejected. For future upgrades, append SQL statement tuples to
`core/schema.py` without changing released migrations.

The recipe editor accepts hours and minutes separately, stored as total minutes.
Each ingredient has its own name, quantity and unit fields; units can be selected
or typed freely. Preparation steps have separate text fields and can be reordered
using the drag handle or the up/down buttons. Numbering follows the saved order.


## Setup

```bash
uv sync
```

The project uses uv and `uv.lock` for environments and reproducible dependencies.
SQLite is provided by Python's standard library; no database service is required.

Project skills live in `.agents/skills/` (read by Codex). Link them for
Claude Code once per clone:

```powershell
# Windows
New-Item -ItemType Junction -Path .claude\skills\przepisnik -Target "$PWD\.agents\skills\przepisnik"
New-Item -ItemType Junction -Path .claude\skills\przepisnik-manage -Target "$PWD\.agents\skills\przepisnik-manage"
```

```bash
# macOS / Linux
mkdir -p .claude/skills && ln -s ../../.agents/skills/przepisnik .claude/skills/przepisnik
ln -s ../../.agents/skills/przepisnik-manage .claude/skills/przepisnik-manage
```

Invoke `$przepisnik` for imports or `$przepisnik-manage` for existing recipes in
Codex (`/przepisnik` and `/przepisnik-manage` in Claude Code). Skills invoke the CLI;
they do not generate scripts or directly write database files for routine operations.

## Migrate existing JSON

These commands migrate a legacy JSON collection into a new database. They do not
upgrade a database created by 1.1.0. The 1.2.0 upgrade path is still pending: its
new `app_state` table is currently created only for new databases. Keep an existing
1.1.0 database and its images backed up; do not rebuild it from stale JSON after edits.

```bash
uv run przepisnik migrate-json --dry-run
uv run przepisnik migrate-json
```

Migration copies all recipes, variants and source records in one transaction. It leaves
the original JSON and images untouched and seeds import identities for existing variants.
Repeating migration skips identical records; an existing differing ID aborts the whole
migration. Imports and browsing refuse to ignore unmigrated legacy JSON.
The preview does not create a database or update files.
Create a separate backup of JSON and images before migration. Migration itself does
not create a backup archive.

## Usage

### Local recipe browser (1.3.0)

```bash
uv run przepisnik serve
```

Open **http://localhost:8000** in your browser. Stop the server with `Ctrl+C`.
Use `serve --port 8080` to choose another port, or the global `--data-dir` option
to browse a different database. The server binds only to the local computer.

The Polish interface provides recipe photos, search by name or ingredient, combined
meal/dish/variant/tag filters, favorites, uncategorized recipes and pagination.
Open a card for ingredients, preparation, nutrition, notes and source details;
switch variants without modifying stored data. Filters are preserved in the URL.
The layout adapts to smaller screens. Use **Dodaj przepis** to create a recipe,
or **Edytuj przepis** in its details to edit ingredients, preparation, nutrition,
categories, tags, favorites and notes. Existing variants and source metadata are retained.
Photos support PNG, JPEG, WebP and GIF up to 8 MB, with a preview before saving.
Recipes without a photo display `data/empty_dish.png`. Editing without selecting
a new photo keeps the existing photo. Conflicting edits from another tab are rejected;
reopen the recipe to load the latest version before editing again.

The application uses Python's standard HTTP server and bundled HTML/CSS/JavaScript,
with no frontend build or additional dependencies.

### Command line

```bash
uv run przepisnik detect "przepisy/Dieta (1).pdf"                 # which parser handles it
uv run przepisnik import "przepisy/Dieta (1).pdf" --variant female --dry-run
uv run przepisnik import "przepisy/Dieta (1).pdf" --variant female
uv run przepisnik schema                                        # draft format for agents
uv run przepisnik add drafts.json --variant family --url https://example.com/recipe
uv run przepisnik dump-text some.pdf --first-page 1 --last-page 2
uv run przepisnik recipes list --meal lunch --variant female
uv run przepisnik recipes list --favorite --query "owsianka"
uv run przepisnik recipes show <recipe-id>
uv run przepisnik recipes favorite <recipe-id> --on
uv run przepisnik variants move <recipe-id> --from male --to female
uv run przepisnik variants copy <recipe-id> --from female --to family
uv run przepisnik recipes update <recipe-id> --patch metadata.json
uv run przepisnik recipes export
uv run przepisnik schema --kind metadata
uv run przepisnik schema --kind recipe
uv run przepisnik check-data
```

Variants: `male` (Mężczyzna), `female` (Kobieta), `family` (Rodzina).
The database location defaults to `./data` (override with `--data-dir` or `PRZEPISNIK_DATA`).

## Data layout

```
data/recipes.sqlite3                   # authoritative recipes, sources, import identities
data/recipes/<recipe-id>/image*.png     # image files; other common formats are supported
data/recipes/<recipe-id>/recipe.json    # retained legacy originals; no longer updated
data/sources.json                      # retained legacy source registry
```

- Steps live on the recipe; a variant has its own `steps` only when they differ.
- Legacy recipe versions are retained. New imports with an existing title but differing
  content are reported as conflicts, never silently versioned or replaced.
- Nutrition and ingredients are per `servings` of the variant (Respo: always 1);
  `suggested_batch_portions` tells how many portions to cook at once.

SQLite stores validated nested recipe documents plus relational indexes for recipe IDs,
title lookup, source records and original import identities. `PRAGMA user_version`
tracks the database schema; recipe documents use `schema_version: 2` and read v1 JSON.

## Categories and user metadata

Meal occasions are independent of dish types and portion variants:

| Field | Values |
| --- | --- |
| `meal_types` | `breakfast` (sniadanie), `lunch` (obiad), `dinner` (kolacja), `snack` (przekaska) |
| `dish_types` | `main`, `soup`, `salad`, `cake`, `bread`, `dessert`, `other` |
| Variant | `male`, `female`, `family` |

Several meal occasions may apply to one recipe. Unknown source categories remain empty.
Respo classifies explicit Polish meal names first, then ranges entirely within 06:00-10:00,
12:00-16:00 or 17:00-22:00 as breakfast, lunch or dinner. Sequence numbers and
"dowolna pora dnia" do not imply a category. The original header and classification
basis (`explicit` or `time_range`) are retained on newly imported variant sources.
These time windows are suggestions, not nutritional facts.

Personal fields live under `user` and cannot be supplied by import drafts. Example
`metadata.json` for `recipes update`:

```json
{
  "favorite": true,
  "notes": "Use less sugar next time.",
  "tags": ["quick", "freezer"],
  "meal_types": ["breakfast", "dinner"],
  "dish_types": ["bread"],
  "preparation_minutes": 40
}
```

Unspecified metadata fields are retained; lists replace the current manual selection.
`meal_types: null` restores source suggestions, while `meal_types: []` explicitly
clears them. Dish types behave the same way. Times must be positive, metrics need
both amount and unit, and empty titles, steps or tags are rejected.

## Import rules

- New title: create a recipe. Same normalized title and exact normalized content: skip.
- Missing variant: add only when ingredient names and preparation identify one existing
  recipe unambiguously. Different quantities are allowed across different variants.
- Existing differing variant, different ingredients, or ambiguous matching versions:
  report a conflict and preserve existing data. There is no `--replace` option.
- Per-item fingerprints ignore provenance, raw ingredient formatting and user metadata.
  Original variant assignments are recorded separately, so moving a variant does not
  cause the next scan of the same content to recreate its previous assignment.
- A source is checked item by item, including previously unresolved conflicts. One
  transaction commits successful items and their receipts; any write failure rolls back
  all database changes in the operation. Conflicts are reported, not treated as writes.
- Existing personal fields and recipe content are never overwritten. To explicitly
  add source meal suggestions to existing recipes, rescan with `--enrich-meals`;
  manual category overrides still take precedence. New recipes accumulate occasions
  from repeated occurrences within the same import.
- `--dry-run` compares without updating the database, registry or images.

Variant moves/copies never scale ingredients or nutrition and refuse an occupied target.
The shared operations accept `expected_updated_at` for optimistic concurrency in the
future editing UI. Bulk editing and web-based editing are not implemented yet.

## Export and backups

`recipes export` prints the complete v2 recipe documents as a JSON list; it does not
include images or the import ledger and is not a complete backup. For a full backup,
close the application and copy the entire `data/` directory, including SQLite and images.
Content-addressed new images are not overwritten. A failed import can leave an
unreferenced image file, but it cannot commit a partial set of recipe records.
`check-data` validates all recipe documents, checks image references and runs SQLite
integrity and foreign-key checks. Conflicts include candidate recipe IDs and the
incoming draft for review with `recipes show`.

## Architecture

- `core/` - shared library: schema, classification, identities, conservative merging,
  SQLite persistence, legacy migration, filters, metadata and variant operations.
  Every source reaches the store through `core.importer.RecipeImporter`.
- `parsers/` - code parsers for frequent, stable formats (`respo`), auto-detected via
  `parsers/registry.py`. Other sources are extracted by the agent skill
  (`.agents/skills/przepisnik`) and added with `przepisnik add`.
- `adapters/` - file format readers (PDF via PyMuPDF).
- `web/` - local HTTP routes and bundled interface; reads use the same store and filters.

## Development

Ruff handles linting (including the `PL` rules derived from Pylint) and formatting;
mypy checks types. Run all checks on Windows with:

```powershell
./scripts/check.cmd
```

The checks do not modify files. To format and check manually:

```bash
uv run ruff format . && uv run ruff check . && uv run python -m mypy src
```
