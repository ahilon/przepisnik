# Changelog

## Unreleased

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
