---
name: przepisnik
description: Imports recipes from diet-plan PDFs, websites, text and photos into this project's SQLite database through the przepisnik CLI. Use when the user says "dodaj przepis", "zaimportuj PDF", "wyciągnij przepisy" or wants to rescan recipe sources. Do not use for editing existing recipes, favorites or variant assignments; use przepisnik-manage instead.
---

# Przepisnik - recipe import

Every source ends up in the same SQLite database, always through the `przepisnik` CLI
(run from the repository root with `uv run przepisnik ...`). Never write or edit files in
`data/` directly. Never write SQL or ad hoc Python to modify recipes. The CLI validates,
compares and commits imports transactionally. Code development is a separate task.

## Language

Talk to the user in Polish. Recipe content (titles, ingredients, steps) stays in the
source language; JSON keys are English.

## Variant assignment

Each source is one variant: `male` (Mężczyzna), `female` (Kobieta), `family` (Rodzina -
whole cake, bread, pot; set `servings` accordingly). Ask only when the variant has not
already been specified for that source in the conversation. Never infer it from a
person's name or greeting; you may show hints
(greeting line, daily kcal) to help them decide.

For a whole folder of Respo PDFs producing a new collection, use the `tool-respo` skill and its reviewed script instead of repeating single-file imports.

## Workflow

1. **Detect:** `uv run przepisnik detect <file>`.
   If the CLI reports legacy JSON, run `uv run przepisnik migrate-json --dry-run`,
   inspect the result, then `uv run przepisnik migrate-json`. Originals are retained.
   These commands migrate legacy JSON, not an existing 1.1.0 SQLite database. If a
   database upgrade is missing, report it; never delete or rebuild the database.
2. **Ask** for the variant (see above).
3. **Built-in parser found** (e.g. `respo`):
   `uv run przepisnik import <file> --variant <v> --dry-run`, show the summary, then run
   without `--dry-run`.
4. **No parser** (website, own recipe, photo, other PDF) - you are the parser:
   - Read the source with available web tools for URLs, `uv run przepisnik dump-text <pdf>`
     for PDFs (use `--first-page/--last-page` to limit output), and file/image tools otherwise.
   - Get the format once: `uv run przepisnik schema`.
   - Write a draft file (JSON list of recipes) in the scratchpad/temp directory.
   - `uv run przepisnik add <drafts.json> --variant <v> (--source <file> | --url <url>) --dry-run`,
     fix validation errors, then run without `--dry-run`.
5. **Report** counts, `enriched_meals`, `conflicts`, and `warnings`.
   - Existing identical content is skipped, including reimports after a variant move.
   - Missing unambiguous variants are added without changing existing metadata.
   - Different content or ambiguous versions remain conflicts. Show them for review;
     never attempt direct writes or automatic new versions. Use `--force` only when the
     user explicitly asks to reimport and overwrite, after a `data/` backup and a
     `--dry-run` reviewed with the user.
   - Repeated sources are checked item by item; previously conflicting items can be retried.
   - Use `--enrich-meals` only when the user requests category enrichment of existing
     recipes. It adds source suggestions while preserving manual category overrides.

## Draft rules (agent extraction)

- Copy values verbatim; never estimate or compute nutrition. Missing values -> omit
  `nutrition`. Values per 100 g instead of per serving -> omit and note it in `notes`.
- `nutrition` and `ingredients` describe `servings` servings (usually 1; `family`: the
  whole dish).
- Ingredients: keep the original line in `raw`; fill `amount`/`unit` (household measure)
  and `metric_amount`/`metric_unit` (`g` or `ml`) only when stated.
- One step per list item, without numbering. Extra information (tips, storage, portion
  hints) goes to `notes`. "Cook N portions at once" -> `suggested_batch_portions`.
- Dish photo: save it next to the draft and reference it in `image_file`. Skip photos
  that are not the dish itself.
- Meal occasions are `breakfast` (sniadanie), `lunch` (obiad), `dinner` (kolacja),
  `snack` (przekaska). Multiple occasions are allowed. Dish types are separate:
  `main`, `soup`, `salad`, `cake`, `bread`, `dessert`, `other`.
- Copy explicit source categories; leave unknown categories empty. Do not infer a
  meal from its sequence number. The Respo parser maps unambiguous time windows and
  retains the original header and classification basis.
- Never include user favorites, personal notes or tags in import drafts.

## New source formats

If the user imports many recipes from one source with a stable layout, suggest writing a
dedicated parser (in `src/przepisnik/parsers/`, registered in `registry.py`) with the
`project-developer` skill instead of extracting each recipe manually.
