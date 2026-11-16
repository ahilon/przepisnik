# Task tools

Tools are reviewed scripts for repeatable jobs. A small project skill supplies
inputs and interprets the result; application validation stays in the shared CLI.
Run tools from an installed checkout (`uv sync --locked`).

| Tool | Script | Skill | Result |
| --- | --- | --- | --- |
| [Respo](respo/README.md) | `uv run --locked python tools/respo/import_recipes.py` | `$tool-respo` / `/tool-respo` | Fresh SQLite collection, photos, report and usage instructions |

Keep personal PDFs under ignored `przepisy/`, generated collections under `data/`
and private alias configuration under `local-artifacts/`. Tools do not publish
collections or insert private recipes into application images.
