---
name: przepisnik
description: Builds the recipe knowledge base of this repository - extracts recipes (title, nutrition, ingredients, steps, dish photo) from diet-plan PDFs (Respo), recipe websites (e.g. aniagotuje.pl), own recipes or photos of recipes, and stores them as JSON with male/female/family variants. Use when the user wants to add, import or extract recipes into the database ("dodaj przepis", "zaimportuj PDF", "wyciągnij przepisy").
---

# Przepisnik - recipe import

Every source ends up in the same JSON store, always through the `przepisnik` CLI
(run from the repository root with `uv run przepisnik ...`). Never write or edit files in
`data/` directly - the CLI validates, merges variants and versions.

## Language

Talk to the user in Polish. Recipe content (titles, ingredients, steps) stays in the
source language; JSON keys are English.

## Variants - always ask

Each source is one variant: `male` (Mężczyzna), `female` (Kobieta), `family` (Rodzina -
whole cake, bread, pot; set `servings` accordingly). Ask the user for every source file,
once per file. Never infer it from a person's name or greeting; you may show hints
(greeting line, daily kcal) to help them decide.

## Workflow

1. **Detect:** `uv run przepisnik detect <file>`.
2. **Ask** for the variant (see above).
3. **Built-in parser found** (e.g. `respo`):
   `uv run przepisnik import <file> --variant <v> --dry-run`, show the summary, then run
   without `--dry-run`.
4. **No parser** (website, own recipe, photo, other PDF) - you are the parser:
   - Read the source: WebFetch for URLs, `uv run przepisnik dump-text <pdf>` for PDFs
     (use `--first-page/--last-page` to limit output), Read for images and text files.
   - Get the format once: `uv run przepisnik schema`.
   - Write a draft file (JSON list of recipes) in the scratchpad/temp directory.
   - `uv run przepisnik add <drafts.json> --variant <v> (--source <file> | --url <url>) --dry-run`,
     fix validation errors, then run without `--dry-run`.
5. **Report** to the user: counts, `new_versions`, `conflicts`, `warnings`.
   - `new_versions`: same title but different ingredients - stored as version 2, 3...
   - `conflicts`: the same variant already exists with different data. Show the
     difference and ask before re-running with `--replace`.
   - "already imported": the identical source was imported before - tell the user.

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

## New source formats

If the user imports many recipes from one source with a stable layout, suggest writing a
dedicated parser (in `src/przepisnik/parsers/`, registered in `registry.py`) with the
`python-dev` skill instead of extracting each recipe manually.
