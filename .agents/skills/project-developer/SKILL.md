---
name: project-developer
description: Implement approved project changes or author tests after behavior is settled; use project-tester for verification and project-github for release metadata and publication.
---

# Project developer

Use one mode at a time: **implement** or **tests**. This skill changes approved files; it does not run verification or package a release.

## Establish scope without repeated approvals

Read the relevant repository instructions, accepted plan or user request, and current diff. An explicit request to implement a concrete behavior authorizes implementation; do not demand another approval just because the request did not use a particular phrase or document template. A request to discuss an idea is planning, not implementation approval.

Reuse existing approval for routine edits and repairs within the same accepted scope. Do not ask per file, function or command. Ask only when a material decision cannot be inferred, behavior/scope must change, or the next phase is not already authorized. State ordinary assumptions in progress updates and keep working where they do not block the task.

Implementation approval does not automatically authorize test authoring. Test-authoring approval does not authorize execution. The user may explicitly authorize both modes in one request; in that case complete implementation, settle the agreed behavior, then author tests without an extra approval loop. Never infer broader authority from loading this skill. Host permission requirements still apply; batch related authorized writes where appropriate rather than requesting one escalation per file.

## Inspect only what the task needs

- Read the affected application code and relevant existing tests/configuration. Inspecting tests to understand behavior is allowed in either mode; executing or modifying them is a separate action.
- Use read-only file/search/Git inspection to understand the current worktree. Preserve unrelated edits and staged files. Do not automatically reset, stash, switch branches or integrate upstream work.
- Follow existing patterns. For schema changes, inspect `src/przepisnik/core/schema.py`; append migrations instead of rewriting released ones. Keep package, recipe-document and SQLite schema versions distinct.
- Never use real recipe data as a development fixture or perform direct writes to the user's database. Use versioned demo fixtures and disposable test data.

## Implement mode

When writing or reviewing Python changes in either mode, read
[references/python-style.md](references/python-style.md) and apply its dependency,
class design, typing and docstring rules to the changed code. Do not restyle
unrelated code as incidental cleanup.

Implement the accepted behavior using the smallest coherent change. Source, configuration, workflow or documentation edits are allowed when they are part of the approved implementation scope. Avoid unrelated refactoring and speculative infrastructure.

Do not author or modify test files/fixtures in this mode. Identify useful scenarios for later instead. Do not execute tests, linters, formatters, type checkers, security scans, builds or application smoke checks. Do not start a server, run migrations/imports, synchronize/install dependencies or invoke application commands as a substitute for tests.

Prefer the standard library and existing direct dependencies declared for the relevant runtime/development context in `pyproject.toml`. Ask before adding or adopting a new direct dependency, including an optional performance library such as NumPy. An entry in `uv.lock` alone may be transitive and is not authorization to depend on it. Explain the benefit, cost and standard-library alternative; existing approval for that named dependency is sufficient. For an approved dependency change, edit the declaration and hand off lockfile/environment synchronization. If implementation genuinely needs an otherwise excluded command, explain the specific need and obtain approval for that exception; existing explicit authorization is sufficient. Do not silently execute it for confidence.

When behavior is ambiguous, resolve the smallest material question before implementing the dependent part. Complete independent approved work meanwhile. Do not redesign the accepted behavior solely to simplify the implementation.

## Tests mode

Enter when the behavior is settled and test authoring is authorized. Use the acceptance criteria and actual regression risks to choose tests. If no test work is warranted, explain why instead of adding tests that only mirror the implementation.

Use pytest for domain/CLI tests and Playwright for browser behavior, following existing fixtures. Read `tests/README.md` and `tests/conftest.py` when changing fixture-dependent scenarios. SQLite and photos must be disposable; a new browser context does not isolate a shared server database. Do not assume current E2E target Docker: inspect the fixtures.

Author meaningful success and failure scenarios for the change, including persistence or migration compatibility when relevant. Do not change expectations merely to agree with new code. Application repairs are allowed only within existing implementation approval; otherwise report the defect and missing scope.

Do not run tests or any other checks in this mode. For browser tests, write scenarios directly; do not start Playwright codegen or the application without a separate explicit request. Report tests as **authored, not executed**.

## Handoff

Neither mode includes version bumps, release-changelog maintenance, commits, pushes, PR creation, merge or deployment. These belong to the separately authorized GitHub/release procedure. Do not automatically invoke it when edits are finished.

Return a short summary of changed files, resulting behavior, material decisions and remaining risks. Clearly state what was not verified; do not call an unexecuted test passing or an unbuilt image working.

For implementation, include proposed later test scenarios and state that tests/checks were not run. For test authoring, list covered scenarios and state that tests are authored but not executed. Hand off the accepted scope, relevant files and unresolved issues to `project-tester` for authorized verification; use `project-github` for separately authorized metadata/publication. Avoid copying the whole conversation or rereading unrelated project documentation.
