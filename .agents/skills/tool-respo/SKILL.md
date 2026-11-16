---
name: tool-respo
description: Build a fresh SQLite recipe collection from a folder of Respo PDFs using explicit variant folders or aliases. Use for whole-folder Respo imports; use przepisnik for single sources and other formats.
---

# Respo collection tool

Talk to the user in Polish. Run the reviewed script from the repository root;
read [tool usage](../../../tools/respo/README.md) for arguments and output layout.
Use `uv run --locked python tools/respo/import_recipes.py`.

- Establish the source folder, a new output folder and explicit variant mappings.
  Standard folder labels are supported; personal names require supplied aliases.
  Ask only about missing assignments. Never infer a variant from a person's name.
- Preview with `--dry-run`. It validates the entire batch in disposable storage.
  Summarize files, mappings, counts, warnings and conflicts. Do not bypass conflicts
  or generate ad hoc extraction/database scripts; the existing parser owns Respo.
- Run without `--dry-run` when import is authorized. An explicit request for both
  preview and import covers both; otherwise obtain approval after the preview.
  Existing output is refused; do not remove it to make a retry succeed.
- Report the exact output directory, per-file results and warnings. Show the
  `check-data` and `serve` commands from generated `USAGE.md`. SQLite and photos
  travel together. Keep private input/output out of commits and application images.

Use `przepisnik-manage` for subsequent recipe metadata/variant changes. This tool
creates collections; it does not deploy, replace or mutate an existing instance.
