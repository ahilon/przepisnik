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

### Container backend in Actions

The `Instance container` job in `.github/workflows/docker.yml` builds the production
image and runs the same browser scenarios against that exact local image ID:

```sh
uv run --locked pytest tests/e2e --container-image "$CONTAINER_TEST_IMAGE" \
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
