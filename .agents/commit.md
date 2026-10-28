# Commit policy

## Scope and branches

Use the staged changes as the commit scope. Keep unrelated user changes unstaged.
Protect `main` and `master`; create an appropriate topic branch when needed.
Use `<type>_<short_english_description>` with feat, fix, docs, refactor, test or chore.
Never stage personal data from `data/`, `przepisy/` or `referencja/`.

## Setup and required checks

Run commands from the repository root against the candidate commit, with isolated test
data. If unrelated working-tree changes could affect results, validate an isolated copy
of HEAD plus the staged changes instead of claiming the working tree proves the index.

1. Run `uv sync --locked` to verify reproducible dependency installation.
2. On Windows run `./scripts/check.cmd`. It runs Ruff lint, Ruff format checking and
   strict mypy. On other platforms run the equivalent commands sequentially:
   `uv run ruff check .`, `uv run ruff format --check .`,
   `uv run python -m mypy src`.

Any required command failure or missing tool/suite stops the commit. Do not silently
skip checks, auto-install pytest, bypass hooks, or expand the change into test setup.
Review automatic formatting/lint fixes before staging them and rerun affected checks.

## Versioning and changelog

Use `[project].version` in `pyproject.toml` and MAJOR.MINOR.PATCH:

| Part | Change |
| --- | --- |
| MAJOR | Breaking changes, major code changes, major release or a large refactor |
| MINOR | New functionality |
| PATCH | Bug fixes, maintenance, documentation, tests, Docker, CI/CD and agent rules |

Every PR must introduce a new package version and a changelog entry, without exceptions
for documentation, tests, infrastructure, formatting or agent instructions. Reset parts
to the right when incrementing MAJOR or MINOR. Use at least PATCH unless the PR requires
MINOR or MAJOR. Compare against the PR target branch (normally main), not an older
release tag. An already sufficient version bump within this same PR need not be repeated
for each commit, but a new PR must have a higher version than its target branch.
If the target changes, recheck before committing. Never downgrade a version.

For every PR add a short English entry in `CHANGELOG.md`, grouped under the new package
version, for example `## [1.4.1] - Unreleased`. Update that PR's entry as its scope changes;
do not add duplicate entries per commit. Review the complete PR scope and final staged
diff against the changelog before committing. Automatically prepare and stage required
version, lockfile and changelog changes while preserving unrelated user edits.
Update README only when user-facing behavior
or documented version status changes; avoid duplicating the changelog there.

After editing the version or dependencies, run `uv sync`, review and stage the intended
changes to both `pyproject.toml` and `uv.lock`, then run the required locked checks.
Do not stage unrelated changes already present in either file.

## Commit and GitHub text

Use a short English subject such as `feat: import recipes from screenshots`.
After the local commit print its branch, hash and check results, followed by a copyable
English GitHub PR title and brief description with actual validation results.
Do not push, publish, create a PR, tag or amend unless the user separately asks.
