---
name: project-tester
description: Review test quality and coverage, then run Ruff, Mypy, non-browser pytest and Checkov for an approved project verification task; report failures without editing code.
---

# Project tester

Review whether the changed behavior is meaningfully tested and execute the quality
checks. Test authoring/repairs belong to `project-developer`; metadata and GitHub
publication belong to `project-github`.

## Scope and approvals

An explicit instruction to verify the agreed change authorizes inspection and the
default suite below, including its normal cache, coverage and temporary outputs.
Do not ask per command or repeat an existing approval. Read-only review alone
does not authorize execution. Respect host permissions and batch related checks
when useful. Do not commit, push, change versions, modify application/tests or
weaken thresholds/ignore rules to obtain success.

Read the intended diff, relevant tests, `pyproject.toml`, `.checkov.yaml` and the
affected workflows. Preserve unrelated work and staged files. Verify the current
environment with `uv sync --locked` when needed; a stale lockfile is a blocker,
not permission to upgrade dependencies. The pinned standalone Checkov environment
is permitted as part of verification. Do not install browser/system dependencies
or run E2E/Docker builds unless that broader scope is explicitly authorized.

## Review tests and coverage

- Compare tests with accepted behavior, including relevant errors, boundaries,
  persistence and compatibility. Flag missing assertions, implementation-mirroring
  tests, excessive mocking and shared mutable fixtures when they affect confidence.
- Use observed coverage and missing branches to identify important gaps; a high
  total does not prove the changed behavior is covered. Distinguish unit/integration
  and browser coverage rather than attributing the whole suite to unit tests.
- Retain the committed coverage threshold (currently 80%). Report actual collected,
  passed, failed, errored, skipped and xfailed counts. Zero collected tests, collection
  errors, unexpected skips or incomplete runs cannot establish readiness. Expected
  exclusions must be explained rather than silently treated as proof of success.
- Use disposable SQLite/databases/photos and versioned fixtures. Never run against
  personal data or a production service. Review existing fixture isolation before
  running newly added tests.

## Default verification suite

Run from the repository root, using current workflow commands/tool pins if changed:

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests/unit
uv run --locked pytest tests --ignore=tests/e2e -p no:cacheprovider --cov --cov-report=term --cov-fail-under=80
uvx --python 3.12 --from checkov==3.4.3 python -m checkov.main
```

Do not use autoformat/fix modes. `scripts/check.cmd` is not the complete suite:
it currently omits pytest and uses a smaller Mypy scope. Checkov's configured
Dockerfile/Actions/secrets checks are not a full image/dependency vulnerability scan.

Stop on a failed required control and report it; do not keep running expensive
dependent checks after a blocker. State which checks were not reached. Retry only
after a relevant change or a concrete transient failure. Separate environment/tool
errors from actual findings, and do not silently drop a failing check.

Browser E2E and Docker smoke/build tests require separate scope. Current browser
fixtures start their own Python server; passing them does not validate an image.
The post-merge stable pipeline is not yet implemented.

## Evidence and handoff

Report each command/outcome, test counts, coverage percentage/threshold, important
uncovered behavior, findings and checks not executed. Distinguish “all executed
checks passed” from “all required checks completed and passed.” Missing tests or
material review gaps must remain visible even when executed checks pass.

Tie evidence to the candidate: baseline commit, relevant dirty/untracked inputs
and environment/lock state. If another phase will reuse the result, record a
content fingerprint/manifest of relevant application, test, configuration and
metadata inputs, excluding generated artifacts and secrets. A matching commit
alone is insufficient for a dirty worktree. Do not claim an isolated candidate
passed based on unrelated local changes that influenced the run.

Hand findings to the developer with expected behavior and minimal failure evidence;
do not silently rewrite tests or requirements. Hand successful evidence to GitHub
for the same candidate. Recheck affected controls after relevant changes, including
release metadata/environment changes; reuse valid evidence instead of rerunning
an unchanged suite solely because a different skill is now active.
