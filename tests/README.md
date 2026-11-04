# Tests

We use **pytest** with **Playwright** for browser end-to-end (E2E) tests.
Tests marked `@pytest.mark.sanity` cover basic application functionality.

Run all commands from the project root.

## Setup

```powershell
uv sync
uv run playwright install chromium
```

Start the application in a separate terminal:

```powershell
uv run przepisnik serve
```

Use a separate test database when testing changes to recipes.

## Record a test

```powershell
uv run playwright codegen --target python-pytest -o tests/e2e/test_recipe_list.py http://localhost:8000
```

Perform the scenario and use the recorder's assertion tools to check expected
text or visibility. Close the recorder to finish, then review the generated test
and give it a descriptive name. The output command overwrites the specified file.

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

Keep the application running while tests execute. Traces are saved under
`test-results/` and can be opened with:

```powershell
uv run playwright show-trace <path-to-trace.zip>
```
