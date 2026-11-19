# Tests

We use **pytest** with **Playwright** for browser end-to-end (E2E) tests.
Tests marked `@pytest.mark.sanity` cover basic application functionality.

## PR sanity and post-merge regression

Pull requests run seven short sanity cases from `e2e/test_sanity.py`: collection
loading/search, recipe details/photo, recipe creation, recipe editing, serving
scaling, shopping quantities after reload and shopping checked-state persistence.
They cover those core journeys only. The remaining browser regressions, including
Wspólne, Dla dwojga, PDF export, conflicts and mobile layout, remain in the full suite.

The PR check keeps its existing name, **E2E tests**, but selects `-m sanity` with
strict markers and requires a positive test collection with every selected case
passed. The release workflow runs after a push to main (normally a PR merge) and
runs the full browser suite without a marker filter against both AMD64 and ARM64
images. Only successful full runs and the other release gates allow stable
publication. No release builds run automatically on PRs.

Run all commands from the project root.

## Setup

```powershell
uv sync
uv run playwright install chromium
```

No external server or Docker container is needed to run the tests. Each test using
`app_page` receives its own database and photos copied from the versioned demo
fixtures into pytest's temporary directory. A local HTTP server starts on a free
loopback port and is stopped during fixture teardown, including after a failure.
Neither the real `data/` directory nor the persistent Docker demo volume is used.
Temporary files can remain under pytest's temporary root according to pytest's
retention policy; they are not reused by later tests.

### Container backend in Actions

The post-merge architecture jobs in `.github/workflows/release.yml` build the
production image and run the complete browser suite against that exact image ID:

```sh
uv run --locked pytest tests/e2e --container-image "$RELEASE_IMAGE_ID" \
  --browser chromium --tracing retain-on-failure --output test-results
```

This opt-in backend requires a local Docker daemon running Linux containers.
It never builds or pulls an image and fails if Docker or image startup fails.
Each test gets a separate container, loopback port, allowed-origin configuration
and bind-mounted disposable data. On Linux, the container uses the non-root data
owner's UID/GID so fixtures can still add recipes from the host. On Windows with
Docker Desktop, it retains the image's default non-root user instead of passing
Windows' synthetic UID/GID. Its healthcheck must pass before
browser navigation. Teardown saves both log streams under
`test-results/container-logs/` and removes the test container even after a failure.
The normal backend above remains the default when no image is specified.
The separate PR `Instance container` job retains Compose/startup/persistence
checks without running another browser suite.

Release jobs additionally use `--release-results <file.json>`. The collector counts
selected test identities, failures across all phases, skips and xfails/xpasses;
`python -m scripts.release verify-tests <file.json>` requires a positive collection
with every selected test passed and exit status zero. Coverage remains a separate
80% gate. Release architecture tests and registry promotion are described in
[docker/RELEASE.md](../docker/RELEASE.md).

In a browser test, request `app_page: Page` instead of `page: Page` and remove any
hardcoded `page.goto(...)`. The `app_page` fixture already opens the application.
Request `app_url` for its address or `recipe_data` for this test's data directory
when needed. A new browser context alone does not isolate the server database.

The session-scoped module-level `base_url` fixture preserves Playwright's CLI/ini
URL settings while avoiding its 0.10.0 instance-method fallback, which emits a
deprecation warning with pytest 9.2. It does not set the isolated server's address;
`app_page` navigates to the per-test `app_url` explicitly.

## Shared browser actions

`tests/ui_actions.py` provides `ApplicationActions` for repeated UI interactions.
Create it with the existing test page; construction does not navigate or modify
data. For example, in a browser test using `app_page`:

```python
from playwright.sync_api import Page, expect
from ui_actions import ApplicationActions


def test_recipe_tag(app_page: Page) -> None:
    """Add a tag to a recipe in this test's disposable demo collection.

    Args:
        app_page: Browser showing this test's isolated demo collection.

    Returns:
        None: The submitted tag is visible on the recipe.
    """
    app = ApplicationActions(app_page)
    title = "Bajgiel z twarożkiem szczypiorkowym i rzodkiewką"
    app.search_product(title)
    app.open_recipe(title)
    app.add_tag("Breakfast")
    expect(app_page.get_by_role("button", name="Usuń tag: Breakfast", exact=True)).to_be_visible()
```

`search_product(query)` searches the recipe catalogue. `open_recipe(title)` opens
an already visible card by its exact title. `add_tag(tag_name)` submits tags only
in the currently open recipe's detail view. Keep these steps separate so each
action also works when a test starts with a recipe already open.

The class also exposes `open_shopping_list()`, `add_product(name, amount, unit)`,
`set_servings(value)`, `add_recipe_to_shopping()` and `show_shopping_list()`.
Open the shopping list before adding a custom product. Open recipe details before
changing servings or adding recipe ingredients; then use `show_shopping_list()`
to follow the recipe's shopping-list link. `open_shopping_list()` uses the main
navigation instead.

Actions wait for the controls they operate on, without fixed sleeps. Keep scenario
assertions, test-data setup, navigation and reloads in the test or its fixtures.
After recording a scenario, replace repeated recorded interactions with these
methods while retaining the generated assertions.

Variant scenarios can also use `open_editor()`, `add_variant(target, source)`,
`save_recipe()` and `merge_variants()`. Audience arguments use `VariantKind`;
copying edits the form only, and saving remains a separate action.
`e2e/test_shared_variants.py` covers explicit deduplication, conflicting portions,
copying unsaved editor values and cancelling additions. Its controlled recipe
comes from `shared_variant_fixtures.py` through the isolated `shared_recipe` fixture.
HTTP regressions additionally exercise stale tokens, origin validation and rollback
when saving source history fails. Unit cases compare ingredient multisets and
preserve quantity, step, serving and nutrition differences.

`e2e/test_tags.py` demonstrates tag persistence after reload, tag filtering with
the search text cleared, and filter visibility in a short desktop window and on
mobile. The visibility assertion runs before interacting with the filter, so
Playwright's automatic scrolling cannot hide a layout regression. These cases
belong to the full regression suite; the seven PR sanity cases remain unchanged.

## Record a test

```powershell
docker compose -f docker/docker-compose.yaml up -d --build --wait
uv run playwright codegen --target python-pytest -o tests/e2e/test_recipe_list.py http://localhost:8001
```

Perform the scenario and use the recorder's assertion tools to check expected
text or visibility. Close the recorder to finish, then review the generated test
and give it a descriptive name. The output command overwrites the specified file.
Recording against Docker changes its demo data. After recording, replace the
generated `page` parameter with `app_page`, assign `page = app_page`, and remove
the recorded initial `goto`. Running the adapted pytest test then uses fresh data.

To include a test in the sanity suite, add `import pytest` and decorate it with
`@pytest.mark.sanity`.

## Run tests

```powershell
# All browser tests
uv run pytest tests/e2e

# PR sanity cases only
uv run --locked pytest tests/e2e -m sanity --strict-markers

# One file, with a visible browser
uv run pytest tests/e2e/test_recipe_list.py --headed

# Keep a trace if a test fails
uv run pytest tests/e2e --tracing retain-on-failure
```

## Unit tests and coverage

Unit tests in `tests/unit` need no browser or server. They build domain objects
with the helpers in `tests/unit/factories.py`, use temporary SQLite databases and
generate small PDF files with a standard-library PDF writer and explicit Unicode
maps. Pillow supplies synthetic image samples; no external fonts or PDF sources
are required. Adapter regressions also use pypdf to construct transformed pages.

```powershell
# Unit tests only
uv run pytest tests/unit

# Coverage of unit and other non-browser tests
uv run pytest tests --ignore=tests/e2e --cov

# Coverage of the whole suite, including browser tests, with an HTML report
uv run pytest tests --cov --cov-report=html
```

Coverage settings (source package, branch coverage, report format) are in
`pyproject.toml` under `[tool.coverage.*]`. The HTML report is written to `htmlcov/`.

The test fixtures start and stop the application automatically. Traces are saved under
`test-results/` and can be opened with:

```powershell
uv run playwright show-trace <path-to-trace.zip>
```
