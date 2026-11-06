# Changelog

## Unreleased

## [1.7.0] - Unreleased

- Clear all checked and unchecked shopping products after confirmation, preserving
  concurrent edits made on another device and disabling the action on an empty list.
- Cover cancellation, persisted clearing and stale-list conflicts with browser tests.
- Accept fractional displayed servings greater than zero and up to 20, with half-portion
  increment/decrement buttons and fractional quantities in the shopping list.
- Test manual fractional values, half steps, bounds and shopping-list scaling while
  keeping original recipe quantities unchanged.
- Hide and restore recipes from their details, with a dedicated hidden collection;
  exclude hidden recipes from ordinary lists, searches, filters, tags and counters.
- Preserve favorites and recipe content on restore, read existing metadata as visible
  by default, and expose an explicit CLI hidden filter without a SQLite schema migration.
- Cover hidden discovery, restoration, CLI filtering and mobile navigation with tests.
- Classify Respo meal slots by number (1 and 3: breakfast and dinner, 2: lunch,
  4: snack) before time-range inference, recorded as `respo_meal_number`.
- Make `RecipeParser` an abstract base class inherited by `RespoParser`.
- Add `--allow-variant-differences` to approve differing content for a missing
  variant of one unambiguous recipe, never overwriting existing variants.
- Show a red notice when male and female preparation steps differ, and label
  Respo sources in recipe details.
- Cover Respo classification, re-import deduplication, variant approval, source
  display and variant step switching with tests.
- Add a Raspberry Pi Docker deployment with a Caddy proxy, maintenance page,
  verified daily OneDrive backups with 14-archive retention and fast-forward updates.
- Cover backup verification, failure handling and retention with a shell test.
- Simplify the favorite browser test.

## [1.6.0] - Unreleased

- Add a shared shopping list with custom products, editable quantities and units,
  checked items, removal, persistence and protection against concurrent updates.
- Add recipe ingredients for the selected servings, combining matching products
  with compatible g/kg and ml/l units while preserving unknown quantities.
- Open shopping from the top bar, simplify decorative labels and show the installed
  package version in the footer.
- Cover shopping storage, validation, recipe isolation, device conflicts and mobile
  browser interactions with isolated tests.

## [1.5.0] - Unreleased

- Add a serving-count control in recipe details to scale known ingredient quantities
  and total nutrition from the selected variant's original servings.
- Keep scaling display-only: preserve stored recipes, editor values, preparation
  text and ingredients without numerical quantities; reset portions on variant
  changes and reopening a recipe.
- Cover scaling, repeated changes, invalid inputs, variant resets and unchanged
  database/editor values with isolated Playwright tests.

## [1.4.4] - Unreleased

- Run browser tests against a fresh temporary recipe database and local HTTP
  server for each test, leaving production and persistent Docker demo data untouched.
- Replace the empty sanity template with favorite persistence/removal coverage
  and checks that recipe mutations do not leak between tests.
- Avoid pytest-playwright's deprecated instance-method base URL fixture while
  preserving CLI/configuration options, and document the isolated test workflow.

## [1.4.3] - Unreleased

- Skip database updates and preserve timestamps when validated recipe content is
  unchanged, including repeated uploads of the same photo.
- Preserve inherited categories and preparation steps when saving unchanged forms,
  and report unchanged saves in the API and browser.
- Make favorites actionable from recipe cards and details, refreshing counters and
  active filters while preserving other recipe content.

## [1.4.2] - Unreleased

- Fixed recipe editor fields over HTTP on home-network addresses by removing
  their dependency on the secure-context-only `crypto.randomUUID()` API.
- Added Playwright and pytest development dependencies, browser test scaffolding,
  recording instructions and ignored test/cache output directories.

## [1.4.1] - Unreleased

- Added an isolated Docker Compose demo with six recipe folders and photos,
  a dedicated data volume, healthcheck and reset instructions.
- Added GitHub code owners for the repository and tests.
- Required a new package version and changelog entry for every PR, including
  documentation, test infrastructure and agent rules.

## [1.4.0]

- Added configurable server addresses and allowed origins for home-network access.
- Added instance setup documentation and repository commit rules.
- Added transactional SQLite migrations with pre-upgrade backups.
- Added hours/minutes and ingredient fields with custom units.
- Added individual steps with drag reordering and up/down controls.

## [1.3.0] - Unreleased

- Added a local recipe browser with search, filters and recipe details.
- Added photo cards, pagination and switching between recipe variants.
- Added a responsive Polish interface, started with `przepisnik serve`.

## [1.2.0]

- Improved data validation and import conflict reports.
- Added database and image integrity checks.
- Improved migration safeguards and meal classification handling.
- Updated documentation and skill instructions.

## [1.1.0]

- Added SQLite storage and migration from JSON.
- Added meal categories, favorites, tags and personal notes.
- Added recipe filtering and variant management.
- Improved imports to avoid overwriting existing recipes.
- Added management skills and code quality checks.
