# Changelog

## Unreleased

## [1.11.3] - Unreleased

- Make @ahilon the sole code owner for every path, removing alternate test owners.
- Define the main ruleset requiring fresh code-owner approval without bypass actors,
  and name the actual Ruff, Mypy, unit, E2E, Checkov and Secrets merge checks.
- Document administrative activation separately from merging CODEOWNERS changes,
  including GitHub's restriction on approving one's own pull requests.

## [1.11.2] - Unreleased

- Replace PyMuPDF with pypdf and Pillow while preserving Respo text positions,
  embedded photos, transparency and original JPEG data without recompression.
- Reassemble adjacent text spans across font changes so split meal headers and
  numbered steps import correctly; add independent synthetic PDF regression fixtures.
- Replace the six demo recipes with newly authored AI-assisted samples and images,
  document their provenance and omit unverified nutrition values.
- License the project under MIT, include the license in packages and container
  images, and document the distinction between code and imported recipe content.

## [1.11.1] - Unreleased

- Gate main image publication on quality/security checks and complete passing
  unit/browser suites for both AMD64 and ARM64, including startup and data persistence.
- Transfer tested images without rebuilding; publish immutable version/commit tags
  and promote stable only after validation, with serialized stale-candidate protection.
- Skip documentation/version-only image releases and document GHCR authentication,
  Raspberry Pi deployment, persistent data, updates and rollback precautions.

## [1.11.0] - Unreleased

- Build fresh Respo collections from PDF folders with explicit portion aliases,
  whole-batch previews, conflict rejection and validated staged publication.
- Bundle SQLite, photos, a JSON import report and usage instructions together.
- Add the shared Codex/Claude `tool-respo` skill and document tool management.

## [1.10.6] - Unreleased

- Separate the default instance image from the explicit demo target, with non-root
  execution, persistent data and read-only server configuration mounted by Compose.
- Check readiness against the configured API host; initialize only empty data and
  require explicit migration before starting with legacy JSON collections.
- Verify instance startup, recipe/photo persistence after recreation and isolated
  container-backed browser E2E in GitHub Actions; support the same fixtures on Docker Desktop.
- Document instance configuration, backup precautions and container test setup.
- Explain recipe collection, AI assistance and shopping workflows in the README;
  centralize shared constants, process execution and scoped lint exceptions.
- Reference checkout consistently as `actions/checkout@v5` across workflows.

## [1.10.5] - Unreleased

- Add a pinned, checksum-verified Gitleaks CLI workflow for all pushes and pull
  requests, including drafts and documentation changes, with redacted output.
- Include Git history, candidate-file and staged-diff secret scans in the tester
  and GitHub procedures, and document the required Secrets check and local setup.

## [1.10.4] - Unreleased

- Share the lead, developer, tester and GitHub workflow between Codex and Claude
  Code, with common approval rules and tracked Claude skill entry points.
- Document Python implementation conventions, test verification and coverage,
  safe Git branch synchronization, PR publication and explicitly approved merge.
- Replace the legacy commit policy with a pointer to the shared workflow and
  update developer setup instructions without changing client permissions.

## [1.10.3] - Unreleased

- Add the `project-github` skill for approved versioning, local verification and
  pull request publication through Git and GitHub CLI.
- Add a developer guide covering required tools, authentication and AI-assisted
  contribution, and refresh the README onboarding instructions.
- Keep local planning artifacts and the Claude GitHub skill link out of Git.

## [1.10.2] - Unreleased

- Check every ready pull request with separate GitHub Actions workflows: Ruff, mypy,
  unit tests with an 80% coverage threshold, Playwright E2E tests, Checkov and, for
  image changes, a Docker build with a healthcheck.
- Run workflows only for pull requests, skip drafts and cancel outdated runs.
- Document the workflows and the checks to require for merging into `main`.

## [1.10.1] - Unreleased

- Add unit tests for the domain model, merging, import, storage, migrations, Respo
  parsing, PDF reading, configuration and the CLI, with pytest-cov coverage settings.
- Scan the Docker image, GitHub Actions workflows and configuration secrets with
  Checkov locally (`scripts/check.cmd`) and in a new CI workflow.
- Move the demo readiness check into the image as a Dockerfile `HEALTHCHECK`.

## [1.10.0] - Unreleased

- Add a "Zupy" shortcut tab that filters recipes by the soup dish type.
- Keep the recipe editor's save and cancel buttons pinned while scrolling.
- Stay on the recipe after adding it to the shopping list and show a confirmation
  with a link to the list.
- Export products still to buy from the shopping list to PDF through the print dialog.
- Show "Wyczyść listę" as a red text action and remove the redundant refresh button.
- Add and remove custom tags in recipe details and the editor, with suggestions from
  existing tags.

## [1.9.1] - Unreleased

- Parse the older quantity-first Respo ingredient layout (`2 sztuki pomidorów (320 g)`,
  `0 -- makaronu (60 g)`) instead of joining all ingredients into one entry.
- Add `--force` to `import` and `add` to re-read imported items and overwrite the
  selected variant of the single recipe with each title, keeping personal fields,
  other variants and photos.

## [1.9.0] - Unreleased

- Add `--allow-variant-differences` to approve differing ingredients and steps for
  a missing variant of one unambiguous recipe, never overwriting existing variants.
- Show a red notice in recipe details when male and female preparation steps differ.

## [1.8.0] - Unreleased

- Classify Respo meals by their number (1 and 3: breakfast and dinner, 2: lunch,
  4: snack) before time-range inference, recorded as `respo_meal_number`.
- Make `RecipeParser` an abstract base class inherited by `RespoParser`.
- Label Respo sources in recipe details.

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
