# Przepiśnik

**Your recipes, your database, your server.**

Przepiśnik is a self-hosted recipe collection for everyday cooking. Bring together
your own recipes, recipes from websites and diet-plan PDFs in one searchable place.
Keep the ingredients, instructions, photos and source details together, then use
that collection to decide what to cook and what to buy.

Run the browser and SQLite database on your own computer or home server, and open
the Polish-language interface from a laptop or phone on your trusted network.
The recipe browser needs no cloud account or separate database service. Your data
is stored in an ordinary directory that you can back up and move to another instance.

## What you can do

- **Collect recipes from different sources.** Add a family recipe in the browser,
  import a supported diet-plan PDF, or ask an AI assistant to extract recipes from
  a website, text or photo. Imports validate the data before saving it.
- **Keep related portions together.** Store female, male and family variants of a
  dish under one recipe, with each variant's ingredients, nutrition and preparation
  differences. Compare variants without keeping separate, disconnected collections.
- **Cook for the number of people you need.** Change the serving count to scale
  known ingredient quantities and nutrition. The original recipe stays intact.
- **Build one shopping list.** Add ingredients using the selected portions, combine
  matching products with compatible units, add custom items and tick off what you
  already have. Export products still to buy with **Eksportuj do PDF**, using your
  browser's **Save as PDF** print destination.
- **Find and organize your collection.** Search by name or ingredient, filter by
  meal, dish, tags and variant, save favorites and notes, and hide or restore recipes.
- **Keep control of storage and hosting.** Use a local server or an instance
  container with persistent data, explicit network settings and your own backups.

For example, collect two portion variants from a diet plan, select the one you
want to cook, adjust it for three people and send its ingredients to the shared
shopping list. Open the list on your phone or save it as a PDF before shopping.

## Work with recipes through AI

Project skills let Codex and Claude Code import and manage recipes through the same
validated CLI used by the application. Talk to the assistant in ordinary language:

```text
$przepisnik Dodaj przepisy z tego PDF-a jako wariant kobieta.
$przepisnik Dodaj mój przepis na zupę z tego tekstu.
$przepisnik-manage Znajdź obiady z kurczakiem i oznacz ten przepis jako ulubiony.
$przepisnik-manage Ukryj ten przepis w mojej kolekcji.
```

Use `$przepisnik` for imports and `$przepisnik-manage` for existing recipes in Codex;
Claude Code uses `/przepisnik` and `/przepisnik-manage`. The assistant can search,
update notes and categories, hide or restore recipes, and move or copy variants.
Hiding removes a recipe from normal browsing while retaining it in **Ukryte**;
permanent deletion is not currently exposed by the recipe commands.

Recipe storage and the browser run on your server. AI assistance runs in your chosen
client; source material you provide to an external AI service is handled by that
service. The [developer guide](#developer-guide) covers client setup and the
separate development-agent workflow.

## Task tools and Respo folders

[Tools](tools/README.md) combine reviewed scripts with small skills for repeatable
jobs. The [Respo tool](tools/respo/README.md) turns a folder of PDFs into a fresh
portable collection: SQLite, photos, an import report and usage instructions.

Name source folders `kobieta`, `mezczyzna` or `rodzina`, or explicitly map aliases
such as `K=female` and `M=male`. The agent never guesses a variant from a name.

```text
$tool-respo Import PDFs from przepisy/plan into data/respo.
Use kobieta and K for female, mezczyzna and M for male. Preview first.
```

Run the same tool without AI:

```sh
uv run --locked python tools/respo/import_recipes.py --source przepisy/plan --output data/respo --alias K=female --dry-run
```

After reviewing the preview, repeat without `--dry-run`. Existing output is never
reused or overwritten; choose a new directory for another build. Failed batches
publish no partial collection. Sources stay untouched. Keep personal PDFs under
ignored `przepisy/`, output under `data/` and private alias config in `local-artifacts/`.

## Hosting and safety

The server listens on loopback by default. LAN access requires an explicit listener
and allowed browser origins; requests also check the Host header. Imports and edits
are validated, conflicting edits are rejected, and the container runs as a non-root
user with its data separate from the image.

There is no built-in login, user authorization or TLS. Use the current server on a
trusted local network; host/origin checks do not make it a public internet service.
See [instance setup](SETUP.md) for network configuration and backups.

## Instance setup

For your own instance, network names and configuration, see [SETUP.md](SETUP.md).
For an isolated Docker environment with six sample recipes, see the
[Docker demo instructions](docker/demo/README.md).
For an instance container with persistent data and its own configuration, see
the [container guide](docker/README.md).

## Database upgrades

SQLite schema upgrades run automatically when opening a database for writing,
including server startup. Existing databases get a `.before-vN.bak` SQLite backup
before an upgrade. All pending steps run in one transaction; a failure rolls back
both schema changes and the version. Read-only commands require an up-to-date
schema; start the server once to upgrade an older database. Newer unsupported
versions are rejected. For future upgrades, append SQL statement tuples to
`core/schema.py` without changing released migrations.

Package versions (see [CHANGELOG.md](CHANGELOG.md)) are independent of recipe
document and SQLite schema versions.

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

### Local recipe browser

```bash
uv run przepisnik serve
```

Open **http://localhost:8000** in your browser. Stop the server with `Ctrl+C`.
Use `serve --port 8080` to choose another port, or the global `--data-dir` option
to browse a different database. The server binds only to the local computer by default; see [instance setup](SETUP.md) for LAN access and configuration.

The Polish interface provides recipe photos, search by name or ingredient, combined
meal/dish/variant/tag filters, favorites, uncategorized recipes and pagination.
Open a card for ingredients, preparation, nutrition, notes and source details;
switch variants without modifying stored data. Filters are preserved in the URL.
The layout adapts to smaller screens. Use **Dodaj przepis** to create a recipe,
or **Edytuj przepis** in its details to edit ingredients, preparation, nutrition,
categories, tags, favorites and notes. Existing variants and source metadata are retained.
The recipe editor accepts hours and minutes separately, stored as total minutes.
Each ingredient has its own name, quantity and unit fields; units can be selected
or typed freely. Preparation steps have separate text fields and can be reordered
using the drag handle or the up/down buttons. Numbering follows the saved order.
Photos support PNG, JPEG, WebP and GIF up to 8 MB, with a preview before saving.
Recipes without a photo display `data/empty_dish.png`. Editing without selecting
a new photo keeps the existing photo. Conflicting edits from another tab are rejected;
reopen the recipe to load the latest version before editing again.

Saving unchanged validated recipe content skips the database update and retains
`updated_at`, including when the same photo is uploaded again. The editor preserves
inherited categories and preparation steps when they are not changed. The API
returns `changed: false` and the browser displays a no-change notice. Saving a real
change and later saving its reversal still performs two updates.

Favorites can be toggled directly using the heart on each card or the button in
recipe details. Both refresh the favorite count and active filters after saving.

Use **Ukryj przepis** in recipe details to move a recipe out of all regular
collections, searches, filters and their counters. Only **Ukryte** lists hidden
recipes; **Przywróć przepis** makes them visible again without losing favorites,
ingredients or notes. Existing recipes default to visible. Hiding is stored in
user metadata without a SQLite schema migration; exports and backups retain the
recipes. The CLI offers `recipes list --hidden` for the same explicit collection.

Recipe details include a serving count that scales known ingredient quantities
and total nutrition from the selected variant's original servings. Scaling affects
only the view: the database, recipe editor and preparation text retain the original
values. Ingredients without numerical quantities retain their source text. Changing
variants or reopening a recipe restores the original serving count.
Displayed servings accept any finite value greater than zero and up to 20,
including fractions such as 0.7. The plus/minus buttons adjust by half a serving.
When male and female variants have different preparation steps, a red notice
identifies the difference. Switching variants displays that variant's ingredients
and preparation; matching instructions do not trigger the notice.

Open **Lista zakupów** in the top bar to manage the shared shopping list. Add
ingredients from recipe details using the selected serving count, or enter custom
products. Edit quantities and units, check products you already have, and remove
individual items. Use **Wyczyść listę** to remove all checked and unchecked products
after confirmation. Compatible units (g/kg and ml/l) are combined for matching names;
metric quantities take precedence over household quantities when both are present.
Unknown amounts remain empty for manual entry. The list is persisted separately
from recipes in the existing SQLite application state and included in full data
backups. Concurrent changes are rejected with a reload prompt instead of silently
overwriting another device's edits. The footer shows the installed package version
generated from `pyproject.toml`.

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
Respo uses its meal numbers: 1 and 3 are both breakfast and dinner, 2 is lunch, and
4 is snack. This source-specific rule takes precedence over time windows and is
retained as `respo_meal_number` alongside the original header.
Unmapped slots fall back to explicit Polish meal names or conservative time ranges
(06:00-10:00, 12:00-16:00, 17:00-22:00). Other source formats do not inherit the
Respo numbering rule. These categories are organizational suggestions, not nutritional facts.

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
  report a conflict and preserve existing data unless `--force` is given.
- `--force` re-reads already imported items and overwrites the selected variant of the
  single recipe with each title (ingredients, nutrition, servings, source and steps).
  Other variants, personal fields, categories and photos are kept; several recipe
  versions sharing a title remain a conflict. Back up `data/` and run `--dry-run` first.
- After reviewing a missing-variant conflict, `--allow-variant-differences` explicitly
  permits different ingredients and variant-specific steps for a single matching
  recipe title. It never overwrites an existing variant or resolves ambiguous
  recipe versions. Use `--dry-run` to inspect the approved addition first.
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
The shared operations accept `expected_updated_at` for optimistic concurrency.
The browser supports individual recipe editing; bulk editing is not implemented.

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
  (`.agents/skills/przepisnik`) and added with `przepisnik add`. Code parsers inherit
  the abstract `RecipeParser` base class; recipe details label Respo sources.
- `adapters/` - file format readers (PDF via PyMuPDF).
- `web/` - local HTTP routes and bundled interface; reads use the same store and filters.

## Developer guide

The project is developed with AI assistance, including Codex and Claude Code,
for planning, implementation and documentation.

For the developer toolchain and AI-assisted PR workflow, see the
[Developer guide](DEVELOPING.md).

### Prerequisites

- [Git](https://git-scm.com/downloads)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) - manages Python,
  the virtual environment and dependencies. A separate Python installation is not
  needed: uv downloads the version from `.python-version` (3.12) when it is missing.

```powershell
# Windows
winget install --id=astral-sh.uv -e
```

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Get the code

```bash
git clone https://github.com/ahilon/przepisnik.git
cd przepisnik
```

To work on or review an existing pull request, fetch its branch by number:

```bash
git fetch origin pull/<number>/head:pr-<number>
git switch pr-<number>
```

With the [GitHub CLI](https://cli.github.com/) installed, `gh pr checkout <number>`
does the same.

### Install dependencies

```bash
uv sync --locked
```

This creates `.venv/` with the application and the `dev` dependency group (pytest,
Playwright, Ruff, mypy). `--locked` installs exactly the versions in `uv.lock`, as CI
does, and fails if `pyproject.toml` and the lock file disagree. Run it again after
pulling changes or switching branches. Prefix commands with `uv run`; activating the
virtual environment is not necessary. SQLite comes with Python's standard library;
no database service is required.

### Run the application

```bash
uv run przepisnik serve
```

Open **http://localhost:8000**. Data is stored in `./data` (ignored by Git) and starts
empty. To work with the six sample recipes used by the tests and the Docker demo,
seed a fresh `data/` directory once:

```powershell
# Windows
New-Item -ItemType Directory -Force data | Out-Null
Copy-Item -Recurse docker\demo\recipes data\recipes
Copy-Item docker\demo\placeholder.png data\empty_dish.png
uv run przepisnik migrate-json
```

```bash
# macOS / Linux
mkdir -p data && cp -R docker/demo/recipes data/recipes
cp docker/demo/placeholder.png data/empty_dish.png
uv run przepisnik migrate-json
```

### Run checks and tests

```powershell
./scripts/check.cmd                       # Ruff, formatting, mypy, Checkov (Windows)
uv run pytest tests --ignore=tests/e2e    # unit tests, no browser needed
```

Browser (E2E) tests use Playwright. Install Chromium once per machine, and again
after a Playwright upgrade in `uv.lock`:

```bash
uv run playwright install chromium        # Linux: add --with-deps for system libraries
uv run pytest tests/e2e                   # starts its own server on temporary data
uv run pytest tests/e2e --headed          # watch the browser
```

The tests do not use `data/` or a running server. See [tests/README.md](tests/README.md)
for recording new tests, sanity tests, coverage and traces, and
[Development](#development) for the individual checks and CI.

### Before opening a pull request

- Run `./scripts/check.cmd` and the tests; CI runs the same checks on every ready PR.
- Add a short entry to [CHANGELOG.md](CHANGELOG.md), which records version history.

### Git identity

Set the author for this repository, especially when the computer is also used
with other GitHub accounts:

```bash
git config user.name "<name>"
git config user.email "<email used by the GitHub account>"
```

### Claude Code and Codex skills

Canonical project skills live in `.agents/skills/` for Codex. Claude Code uses
tracked entry points in `.claude/skills/` that reference the same instructions;
no per-machine junction setup is required. Both clients share `AGENTS.md`, imported
by `CLAUDE.md` for Claude compatibility.

Start development planning with `$project-lead` in Codex or `/project-lead` in
Claude Code. See the [Developer guide](DEVELOPING.md) for phase approvals, the
developer/tester/GitHub roles and migration from older skill links.

Invoke `$przepisnik` for imports or `$przepisnik-manage` for existing recipes in
Codex (`/przepisnik` and `/przepisnik-manage` in Claude Code). Skills invoke the CLI;
they do not generate scripts or directly write database files for routine operations.

## Development

Ruff handles linting (including the `PL` rules derived from Pylint) and formatting;
mypy checks types. Lint policy lives in `pyproject.toml`: the explicit `return None`
convention is shared across the project, while intentional test/security exceptions
are limited to named files with an explanation. A separate Pylint configuration is
not used by these checks. Run the Windows lint/type/infrastructure checks with:

```powershell
./scripts/check.cmd
```

The checks do not modify files. To format and check manually:

```bash
uv run ruff format . && uv run ruff check . && uv run python -m mypy src
```

Checkov statically checks the Docker image and GitHub Actions workflows for insecure
configuration, and scans configuration files (not Python sources) for committed
secrets. It runs as a separate pinned tool, not a project dependency, using the
settings in `.checkov.yaml`:

```bash
uvx --python 3.12 --from checkov==3.4.3 checkov
```

`scripts/check.cmd` and the `Checkov` GitHub workflow run the same scan.

### Continuous integration

Each pull request runs separate GitHub Actions workflows. Ruff, Mypy, tests and
Checkov skip drafts until ready for review. Secrets runs on every push and PR,
including drafts and documentation changes. Newer updates cancel outdated runs
of the same workflow/ref; Secrets keeps push and PR runs separate.

| Workflow | Check name | Runs | Purpose |
| --- | --- | --- | --- |
| `lint.yml` | Ruff | every PR | Ruff lint and formatting |
| `typecheck.yml` | Mypy | every PR | Strict mypy for `src` and `tests/unit` |
| `tests.yml` | Unit tests | every PR | Non-browser tests with at least 80% coverage |
| `e2e.yml` | E2E tests | every PR | Playwright scenarios; traces uploaded on failure |
| `checkov.yml` | Checkov | every PR | Dockerfile, workflow and secret checks |
| `secrets.yml` | Secrets | every push and PR, including drafts | Gitleaks scans fetched Git history with redacted output |
| `docker.yml` | Docker build / Instance container | PRs changing the image or tests | Checks demo readiness, instance startup/persistence and browser E2E against the image |

Require Ruff, Mypy, Unit tests, E2E tests, Checkov and Secrets in the `main` branch ruleset.
Keep Docker build optional: path-filtered workflows do not run on unrelated pull
requests, and a required check that never runs blocks merging. `tests.yml` can also
be called by other workflows (`workflow_call`), and every workflow can be started
manually (`workflow_dispatch`).
