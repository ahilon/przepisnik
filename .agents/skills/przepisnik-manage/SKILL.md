---
name: przepisnik-manage
description: Browses and manages existing recipes in this project's SQLite database using validated CLI commands. Use when the user requests favorites, personal notes, tags, meal categories, finding recipes, or moving/copying male/female/family variants, e.g. "oznacz jako ulubione", "zmien na kobiete", "pokaz obiady". Do not use for importing sources or implementing application code.
---

# Przepisnik management

Talk to the user in Polish. Run commands from the repository root. Never write SQL,
edit data files, or generate scripts to perform routine recipe operations.

## Find before changing

- `uv run przepisnik recipes list --query "owsianka"`
- `uv run przepisnik recipes list --meal lunch --variant female --favorite`
- `uv run przepisnik recipes show <id>`

Use a returned stable recipe ID. Ask which recipe when a name matches multiple IDs.
Meal values: `breakfast` = sniadanie, `lunch` = obiad, `dinner` = kolacja,
`snack` = przekaska. Dish types: `main`, `soup`, `salad`, `cake`, `bread`,
`dessert`, `other`. Family is a portion variant, not a dish type.

## Update through commands

- Favorite: `uv run przepisnik recipes favorite <id> --on` (or `--off`).
- Move assignment: `uv run przepisnik variants move <id> --from male --to female`.
- Copy assignment: `uv run przepisnik variants copy <id> --from male --to female`.

Moves and copies preserve quantities, nutrition, preparation and source provenance.
If the destination exists, report the conflict; never replace it or improvise a merge.

For metadata, write a temporary JSON object containing only requested fields, then run:

`uv run przepisnik recipes update <id> --patch <temporary-patch.json>`

Allowed fields: `favorite`, `notes` (personal text), `tags` (list of strings),
`meal_types`, `dish_types`, `preparation_minutes` (positive integer or null).
Category lists replace manual selections. `[]` clears a selection; `null` restores
source suggestions. Read the recipe first when adding to an existing list.
Unspecified fields are preserved. Import never overwrites these user fields.

Report the result returned by the CLI. On validation or conflict errors, explain the
message without retrying with weakened rules. Batch edits are not implemented;
do not advertise them as atomic.
