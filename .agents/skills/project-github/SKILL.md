---
name: project-github
description: Prepare an up-to-date task branch, publish verified changes as a PR, or merge a specifically authorized PR using Git and GitHub CLI.
---

# Project GitHub

Use `git` for local repository operations and `gh` for GitHub access. This skill prepares completed work for review; it does not implement features or write tests.

## Authorization and scope

Read-only inspection and drafting PR text do not authorize publication. Before mutations, establish the intended files, branch/base, version bump and whether the user requested preparation only or commit/push/PR creation. Reuse existing explicit approval. A concrete instruction to prepare and publish the agreed change covers the full procedure below without per-command approval; merge is separate.

Do not change source/tests or weaken checks to fix a failure. Stop publication and report actionable evidence. Request additional scope only when the needed repair is not already authorized. Do not bypass host permissions.

## Inspect and prepare

Use **prepare**, **publish** or **merge** mode; do not infer the next mode is
authorized merely because this skill is active. In prepare mode, follow
[references/git-preparation.md](references/git-preparation.md), report the branch,
base and stash outcome, then stop. No release metadata, checks, commit or push is
included. In publish mode, recheck branch/PR freshness with that same procedure
before the following metadata and verification steps. In merge mode, follow
[references/merge.md](references/merge.md) only after explicit authorization.

1. Read relevant repository instructions and inspect `git status --short`, the intended diff/staged files, branch, remotes and recent history. Preserve unrelated changes. Only the preparation reference authorizes a named stash/restore; never reset, silently rebase or force push. Never sweep all dirty files into a commit.
2. Verify tools and identity with `uv --version`, `gh --version`, `gh auth status --hostname github.com`, and `gh repo view --json nameWithOwner,url,viewerPermission,defaultBranchRef`. Check Git author identity separately. Do not show tokens, change credentials or request login secrets in chat.
3. Resolve the target base and branch/PR state, including merged or deleted branches, using the preparation reference. Do not reuse a completed PR's branch or assume an earlier permission to publish that PR covers a new task.
4. Create/switch to `<type>/<kebab-case-summary>` before metadata edits, optionally including an issue number. Types: `feat`, `fix`, `docs`, `skill`, `workflow`, `test`, `refactor`, `perf`, `build`, `chore`. Reuse the branch for the same task on retries. Never publish directly to the protected base.
5. Update `[project].version` in `pyproject.toml` once per PR relative to the current base: major for breaking compatibility or explicit user direction, minor for a compatible feature, patch for compatible fixes and this project's docs/skill/workflow/test/maintenance changes. The highest required bump wins. A large internal refactor alone does not require major. Do not bump again for follow-up commits to the same PR; reconsider if the base or scope changes.
6. Add a short effect-oriented entry to `CHANGELOG.md` in its existing style. Describe what changed and relevant migration requirements; do not invent a release date or rewrite historical entries as incidental cleanup.
7. Run `uv sync` and review `uv.lock` for the intended metadata/dependency changes. Do not perform unsolicited dependency upgrades. Installed package metadata supplies the application's version.

## Verify the final candidate

After finalizing metadata and environment synchronization, use the
[project-tester](../project-tester/SKILL.md) procedure for test review, coverage and
the required local checks. The approved PR-publication phase includes this
verification; do not request another phase approval or launch a separate agent
just to run the procedure. Do not execute automatic formatting fixes.

Reuse an existing tester report only when its recorded inputs/environment match
the final candidate and all required checks completed. A previous run before the
version, lockfile or source changed is insufficient. Recheck affected controls
when evidence is stale; do not duplicate a valid unchanged run merely because
control passed to this skill. If the tester skill is unavailable, report the
missing prerequisite rather than silently skipping verification.

Stop before commit/push/PR on a failed, missing or incomplete required local check. Keep evidence tied to the final candidate. If other dirty files influence checks, isolate the intended candidate without moving or discarding user work; do not claim the committed candidate passed solely from a different working tree. Recheck affected controls after edits, and repeat the suite after upstream integration invalidates the previous result. Avoid retries without a concrete reason.

Local browser E2E are outside this skill's default execution scope. Inspect their remote results: currently `.github/workflows/e2e.yml` runs on PRs and starts its own Python server. A post-merge container release pipeline is planned but not implemented. Do not claim browser tests or image publication passed without evidence.

## Commit, push and create the PR

Only execute the operations authorized by the user:

- Review and stage only agreed files. Use `<type>(<optional-scope>): <summary>` for the commit and PR title; mark breaking changes with `!` or `BREAKING CHANGE:`. Do not add local artifacts, personal recipe data or credentials.
- Before commit, scan the final staged diff with `gitleaks git --pre-commit --staged --config .gitleaks.toml --redact=100 --no-banner .`, using the version pinned in CI. A prior clean history scan does not cover newly staged content. Stop on findings or an incomplete scan; report only redacted locations, never raw secrets.
- Push the task branch with its upstream. Before creating a PR, check for an existing open PR for the same head/base. For an existing PR, reuse it rather than create another; update its title/body only within the authorized scope.
- Write a UTF-8 PR body file under ignored `local-artifacts/` (or the system temporary directory), preserving real newlines. Pass the body through `--body-file`, never shell-interpolate multiline content.

```text
gh pr create --base <base> --head <branch> --title <title> --body-file <file>
```

- Do not use `gh pr create --dry-run` as a read-only preview; it can still push. Before retrying a failed network command, verify whether the push or PR creation already succeeded.
- Use `gh pr view <number> --json url,headRefOid,statusCheckRollup` and `gh pr checks <number>` to report the published SHA and remote outcomes. Checks may not appear immediately. Pending, skipped or absent checks do not establish success. Treat `gh` exit codes with their documented meaning, not every nonzero result as a tooling failure. Do not wait indefinitely or continuously rerun workflows.

The PR body should explain the problem/result, material implementation details, version bump, actual validation and limitations. Return the PR URL, commit SHA, version before/after, local results and remote status. Distinguish “PR opened, CI pending” from “required CI passed.”

Do not merge, enable auto-merge, publish releases, move stable tags, change repository protection or deploy as part of PR publication. A later explicit merge request uses merge mode and current required-check evidence.

If access blocks a step, state what completed and provide the prepared title/body when useful. Never claim a branch/PR exists without checking the result. Organization or token permission failures require targeted user action, not broader credential grants by default.
