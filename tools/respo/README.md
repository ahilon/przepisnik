# Respo folder import

Create a **new** recipe collection from a folder of Respo PDFs using the existing
parser and validated CLI. No additional Python dependencies are required.

```text
przepisy/plan/
  kobieta/week-1.pdf
  mezczyzna/week-1.pdf
  K/week-2.pdf
```

Default labels are `kobieta`/`female`, `mezczyzna`/`mężczyzna`/`male` and
`rodzina`/`family`. Labels are case-insensitive and apply to ancestor folders,
including the supplied root folder. The tool never guesses from a person's name.
Missing or contradictory assignments fail before any import. Symlinks are rejected.

## Preview and build

Run from the repository root:

```sh
uv sync --locked
uv run --locked python tools/respo/import_recipes.py --source przepisy/plan --output data/respo --alias K=female --dry-run
uv run --locked python tools/respo/import_recipes.py --source przepisy/plan --output data/respo --alias K=female
```

For PDFs directly in an otherwise unlabelled folder, use `--variant female` (or
`male`/`family`) as an explicit fallback. Recognized labels take precedence.
Supply repeatable `--alias folder=variant` flags, or copy
[aliases.example.toml](aliases.example.toml) to an ignored local path and pass
`--config local-artifacts/respo-aliases.toml`. Explicit CLI aliases override config
and built-in aliases.

Preview builds the whole collection in disposable temporary storage, so conflicts
between different PDFs are detected as well. It writes nothing to the output or
its parent. Actual import builds in temporary storage alongside the output, then
renames the completed collection after all files and `check-data` succeed. Existing
output directories are refused, including empty ones. Sources remain unchanged.
Choose a new output path for another build; this tool does not update an instance.

Conflicts, malformed PDFs and PDFs with no extracted recipes fail the batch.
No partial collection is published. The JSON response contains completed per-file
reports and parser warnings. Review warnings even after a successful import; the
tool never enables `--force` or guesses how to resolve conflicting recipes.

## Use the collection

The result contains `recipes.sqlite3`, recipe photos under `recipes/`,
`empty_dish.png`, `import-report.json` and `USAGE.md`. Keep the **whole directory**.

```sh
uv run przepisnik --data-dir data/respo check-data
uv run przepisnik --data-dir data/respo serve
```

Open `http://localhost:8000`. For Docker, mount the entire collection at `/data`,
prepare write access for UID/GID 10001 and use your own read-only server config;
see [the instance guide](../../docker/README.md). Do not copy just the SQLite file
or bake personal PDFs/recipes into a distributable image. Back up data before
moving it into an existing instance.

## AI invocation

```text
$tool-respo Import PDFs from przepisy/plan into a new data/respo collection.
Use kobieta and K for female, mezczyzna and M for male. Preview first.
```

Codex uses `$tool-respo`; Claude Code uses `/tool-respo`. Both read the same
canonical instructions. Give the agent explicit permission to execute the import
after reviewing the preview, or authorize preview and import together.
