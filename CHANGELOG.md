# Changelog

## Unreleased

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
