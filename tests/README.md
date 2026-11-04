# Tests

We use **pytest** with **Playwright** for browser end-to-end (E2E) tests.
Tests marked `@pytest.mark.sanity` cover basic application functionality.

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

In a browser test, request `app_page: Page` instead of `page: Page` and remove any
hardcoded `page.goto(...)`. The `app_page` fixture already opens the application.
Request `app_url` for its address or `recipe_data` for this test's data directory
when needed. A new browser context alone does not isolate the server database.

The session-scoped module-level `base_url` fixture preserves Playwright's CLI/ini
URL settings while avoiding its 0.10.0 instance-method fallback, which emits a
deprecation warning with pytest 9.2. It does not set the isolated server's address;
`app_page` navigates to the per-test `app_url` explicitly.

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

# Sanity tests only
uv run pytest tests/e2e -m sanity

# One file, with a visible browser
uv run pytest tests/e2e/test_recipe_list.py --headed

# Keep a trace if a test fails
uv run pytest tests/e2e --tracing retain-on-failure
```

The test fixtures start and stop the application automatically. Traces are saved under
`test-results/` and can be opened with:

```powershell
uv run playwright show-trace <path-to-trace.zip>
```
