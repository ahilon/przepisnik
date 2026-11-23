# Developer guide

This guide covers local tools and AI-assisted contribution to przepisnik. For
application setup, see [README.md](README.md); for instance/network configuration,
see [SETUP.md](SETUP.md).

## Required tools

| Tool | Purpose |
| --- | --- |
| Git | Checkout, branches and commits |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Python, locked dependencies and project commands |
| [GitHub CLI](https://cli.github.com/) (`gh`) | Repository access, pull requests and CI inspection |
| [Gitleaks](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1) 8.30.1 | Local secret scanning before publication; CI installs its verified binary |
| Codex or Claude Code | Optional AI assistance using repository skills |
| Docker with Compose | Needed when building or testing containers, not for unit tests |
| Playwright Chromium | Needed for local browser E2E, not for the default GitHub skill checks |

Python follows `.python-version`; uv can install it when missing. Run commands
from the repository root. There is no need to activate `.venv` manually.

### Windows setup

Install missing tools with WinGet, or use their official installers:

```powershell
winget install --id Git.Git --exact --source winget
winget install --id astral-sh.uv --exact --source winget
winget install --id GitHub.cli --exact --source winget
```

Restart the terminal window and IDE after installation to refresh PATH.

```powershell
git --version
uv --version
gh --version
uv sync --locked
```

`uv sync --locked` installs the application and development dependencies without
updating the lockfile. Use it after checkout or pulling changes. An intentional
metadata/dependency update uses `uv sync`, followed by review of `uv.lock`.

### GitHub authentication

Skip login if the intended account is already authenticated:

```powershell
gh auth status --hostname github.com
gh auth login --hostname github.com --git-protocol https --web
```

The second command is only needed when login is missing or needs repair. Complete
the browser flow yourself; do not paste tokens into agent conversations.

For HTTPS, `gh auth setup-git --hostname github.com` optionally configures Git to
use gh as its credential helper. Keep an existing working credential setup if
preferred. SSH remotes still use SSH keys; this does not convert them to HTTPS.

```powershell
git remote -v
gh repo view --json nameWithOwner,url,viewerPermission,defaultBranchRef
git config user.name
git config user.email
```

Check the repository, active GitHub account and local Git author. Authentication
does not grant additional repository privileges. With an OAuth login, publishing
workflow changes may require `gh auth refresh --hostname github.com --scopes workflow`.
Organization policies may require additional authorization.

Official references: [login](https://cli.github.com/manual/gh_auth_login),
[Git credentials](https://cli.github.com/manual/gh_auth_setup-git),
[additional scopes](https://cli.github.com/manual/gh_auth_refresh).

## Available project skills

Skills are reusable instructions for the current agent, not automatically
separate processes or permission boundaries. Only these skills are currently
implemented in the repository:

| Skill | Use |
| --- | --- |
| `project-lead` | Discuss architecture and coordinate approved phases without direct edits in the lead role |
| `project-github` | Verify finished work, prepare version/changelog and publish an authorized PR through Git/gh |
| `project-developer` | Implement agreed changes or author tests in separately authorized modes, without executing checks |
| `project-tester` | Review test quality/coverage and run Ruff, Mypy, non-browser pytest, Checkov and Gitleaks |
| `przepisnik` | Import recipes using the application CLI |
| `przepisnik-manage` | Browse/manage existing recipes using the application CLI |

`project-lead` combines architecture and orchestration. Both clients use the same
sequential procedures and approval state, normally in one session. Separate agents
are optional and require explicit authorization and host support. This setup does
not change sandbox permissions or guarantee filesystem isolation for the lead.

### Start with the lead

In Codex, use `$project-lead`; in Claude Code, use `/project-lead`:

```text
Use project-lead to discuss the Docker release pipeline. Summarize a concrete
plan and wait for my approval before implementation.
```

The lead presents the plan in conversation and does not edit files while planning.
After plan approval, it hands off to GitHub prepare mode, then developer implement
mode. It returns the implementation for discussion and waits until you declare
the behavior ready for tests. Your request to add and verify tests covers developer
test authoring followed by the tester; narrower requests such as “author only”
remain narrower. After verification it summarizes readiness and asks before PR
publication. Actual merge of a specified PR needs separate explicit approval.

The lead maintains goal, decisions, scope and phase approvals in conversation.
It loads the next canonical skill transparently; loading a skill is not proof that
an independent agent process was spawned.

### Codex

Project skills live in `.agents/skills/`. Open/reload a project session after
adding a skill if it is not listed. Invoke the GitHub skill explicitly:

```text
Use $project-github to inspect the current diff and propose a PR scope,
branch name and version bump. Do not modify files or publish yet.
```

After reviewing that concrete proposal:

```text
Use $project-github to prepare and publish the agreed PR, including the
approved version bump, changelog, uv sync, checks, commit and push.
Do not merge.
```

A skill may also be selected when a matching task is requested in plain language.
Selection alone does not authorize changes or publication. Existing explicit
approval covers the agreed phase; the agent should not ask for every command.
New scope, merge and deployment are separate decisions. Host permission prompts
still apply.

### Developer: implementation and test authoring

Use `project-developer` in one mode at a time. An explicit request covering a
concrete implementation is approval to make those changes; no additional approval
document or per-file confirmation is required.

```text
Use $project-developer in implement mode to add the agreed recipe filter.
Keep the current scope; do not write or run tests yet.
```

Once the behavior is settled, authorize test authoring:

```text
Use $project-developer in tests mode to add regression tests for the agreed
filter behavior. Author the tests without executing them.
```

You may authorize both phases in one concrete request. Otherwise moving from
implementation to test authoring requires approval; execution belongs to
`project-tester` and publication to `project-github`. The developer reads relevant tests but does not run tests,
linters, builds, application smoke checks or dependency synchronization in either
mode. An explicitly authorized exception can cover a necessary command. Existing
approval continues to cover repairs within the accepted implementation scope.

The handoff states which files changed, what behavior was implemented, what test
scenarios were authored/proposed and what remains unverified. Test authoring alone
must never be reported as a passing test run. Neither developer mode bumps the
release version or creates commits/PRs.

Developer conventions are maintained in
[Python style](.agents/skills/project-developer/references/python-style.md): standard
library first, approval for new direct dependencies, cohesive classes, descriptive
names, focused private helpers, shallow branching, simple comprehensions, explicit
`return None`, scoped constants, type annotations and Google-style docstrings.
Existing direct dependencies may be used in their declared context; merely being
transitive in `uv.lock` is insufficient. Properties represent object state or
derived attributes, not an alternative to all function arguments.

### Tester: review and verification

```text
Use $project-tester to review tests for the agreed change and run the default
quality suite. Report coverage and missing scenarios; do not modify files.
```

The tester checks meaningful assertions and gaps, then runs Ruff lint/format
checks, Mypy, non-browser pytest with the existing coverage threshold, Checkov
and Gitleaks.
Generated coverage/cache/temp files are expected; application/test edits are not.
On failure it reports the cause and unexecuted checks, leaving repairs to the
developer. E2E and Docker builds require explicit additional scope.

The GitHub publication phase includes the tester procedure after finalizing
version/changelog and syncing the environment. Valid evidence for the identical
candidate may be reused; metadata or source changes can invalidate earlier runs.
Changing skill does not itself justify running the same checks twice.

### Secret scanning

The `Secrets` workflow runs Gitleaks 8.30.1 on PRs, including drafts and
documentation-only changes, and on pushes to main. It uses a full-history checkout,
upstream default rules extended by `.gitleaks.toml`, a pinned CLI archive SHA-256
and redacted output.
No Gitleaks Action license or extra repository token is required. Add `Secrets`
to the base-branch required checks after its first successful CI run; adding the
workflow file alone does not enforce branch protection.

Install the official CLI for your OS from the linked release and verify its
archive against the release checksums. Add it to PATH or give the agent its full
executable path. Match the version pinned in `secrets.yml`; Windows x64 archive
SHA-256 for 8.30.1 is
`d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e`.

```text
gitleaks version
gitleaks git --config .gitleaks.toml --redact=100 --no-banner --log-opts="--all" .
```

History scanning does not include unstaged/untracked content. The tester also
scans a disposable snapshot of the intended candidate's tracked and nonignored
untracked files using `gitleaks dir --config <repo>/.gitleaks.toml --redact=100
--no-banner <snapshot>`. Exclude ignored personal data, environments and local
artifacts by selecting Git-managed candidate files, not by suppressing their
paths globally in detection rules.

After staging the final candidate, the GitHub role also runs:

```text
gitleaks git --pre-commit --staged --config .gitleaks.toml --redact=100 --no-banner .
```

Scan results may identify sensitive files. Keep reports in ignored local artifacts
with full redaction; do not upload raw findings as CI artifacts or paste secrets
into chat. A finding stops publication; revoke/rotate real credentials rather
than adding them to an ignore list. A clean scan covers supported patterns and
the scanned refs/files, not a complete privacy audit or proof that every IP,
email, password or binary attachment is safe.

### Claude Code

`CLAUDE.md` imports the shared `AGENTS.md`. Tracked entry points in
`.claude/skills/<name>/SKILL.md` tell Claude to read the corresponding canonical
`.agents/skills/<name>/SKILL.md`. These are small adapters, not duplicated role
implementations, and work without symlinks/junctions after checkout.

Invoke `/project-lead`, `/project-developer`, `/project-tester` or `/project-github`.
Recipe entry points are `/przepisnik` and `/przepisnik-manage`. Reload the client if
a newly added skill is not listed. Codex uses the matching `$name` invocations.

Older clones may have ignored junctions/symlinks at these paths. Inspect and migrate
only those links before checking out the tracked adapter files; never recursively
delete their canonical targets. Do not overwrite an existing real skill directory.

The portable implementation does not configure native Claude/Codex agent processes,
models or permissions. An unavailable native skill call can be replaced by reading
and following its canonical file in the same session, with the same phase limits.

References: [OpenAI skills](https://learn.chatgpt.com/docs/build-skills),
[Claude skills](https://code.claude.com/docs/en/skills),
[shared instruction imports](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools).

### Git preparation and merge

Plan approval authorizes `project-github` prepare mode before implementation.
It checks branch/PR state, snapshots dirty work with a named stash when needed,
fetches/prunes, fast-forwards the verified base and creates/reuses the appropriate
task branch. It restores the recorded stash and stops on conflicts/divergence.
Ignored personal data is not stashed. Remote deletion alone is not proof of merge.
See [Git preparation](.agents/skills/project-github/references/git-preparation.md).

Prepare mode does not bump versions, run tests, commit or publish. Publish mode
rechecks freshness before finalizing metadata and verification. Merge mode requires
explicit approval of a specific PR and current remote protection/check evidence;
see [merge procedure](.agents/skills/project-github/references/merge.md).

## What the GitHub skill does

1. Inspects the intended diff, base, repository, identity and existing branch/PR.
2. Creates/reuses a task branch such as `skill/github-pr-workflow`.
3. Updates `pyproject.toml`, a short changelog entry and the environment/lockfile.
4. Uses the tester procedure for Ruff, Mypy, non-browser pytest with coverage,
   Checkov and Gitleaks. A failure stops publication; the skill does not silently
   rewrite application code/tests or weaken checks.
5. Commits only the agreed files, pushes the branch and creates/reuses a PR with
   `gh`. Reports the PR URL, version, SHA and local/remote verification status.

The exact verification commands live in the
[tester skill](.agents/skills/project-tester/SKILL.md); committed workflows and tool
configuration take precedence when commands change. `scripts/check.cmd` is a
convenience command, not the whole PR verification suite.

Default local verification excludes browser E2E. GitHub runs seven isolated
Python-server sanity cases on PRs; the existing check name remains E2E tests.
The [release workflow](docker/RELEASE.md) runs after merge to main, validates the
full browser suite against AMD64/ARM64 and publishes only the tested image pair.
PR sanity does not prove full regression or registry publication. For E2E setup, see
[tests/README.md](tests/README.md).

## Branches and versions

After a PR is merged into `main`, the `PR product version` workflow adds a bot
comment such as `Product version: **1.13.0**`. It reads `pyproject.toml` at that
PR's merge commit, without checking out or executing PR code. Reruns update the
existing marked bot comment. Closed, unmerged PRs are ignored, and historical
merges are not backfilled. This records the merged code version; it does not
confirm image publication or deployment.

Branches use `<type>/<kebab-case-summary>`. Commit messages and PR titles use
`<type>(<optional-scope>): <summary>`. Types are `feat`, `fix`, `docs`, `skill`,
`workflow`, `test`, `refactor`, `perf`, `build` and `chore`.

During an authorized PR publication, the GitHub skill adds the label mapped from
the PR title type through `gh`, preserving existing labels. The canonical
[PR label mapping](.agents/skills/project-github/references/pr-labels.md) defines
`fix`, `skill`, `test`/`tests`, `feat`, `docs`, `chore`, `workflow` and `build`;
other types have no automatic label until a mapping is agreed. Type labels add no
CI check. A separate metadata-only close/reopen workflow keeps `rejected` on
closed, unmerged PRs and removes it when a PR is reopened or merged. It preserves
other labels and does not run PR code.

- Major: breaking compatibility, or an explicit major-release decision.
- Minor: new compatible functionality.
- Patch: compatible fixes and, by project convention, docs/skills/workflows/tests
  and maintenance changes.

Use one bump per PR, not per commit or retry. A big internal refactor alone does
not imply major. Base changes can require adjusting a proposed version. A version
in an open PR is not proof that an image was released. Patch bumps for docs are a
project convention, not a SemVer requirement; the future release workflow must
distinguish documentation-only metadata bumps from runtime changes.

## Worktree and data boundaries

Keep unrelated work out of the PR. Never use a blanket stage/reset to solve
a dirty worktree. Only the authorized Git preparation procedure may stash and
restore its recorded snapshot. If unrelated edits affect validation, isolate the intended
candidate and ensure the evidence applies to its actual content before claiming
success.

Do not commit `local-artifacts/`, real recipe data, personal diet plans or
credentials. Tests use disposable fixtures. Repository skills must not perform
routine direct database edits; use the existing recipe skills/CLI instead.

Auto-merge, GitHub releases, stable-tag promotion and production deployment remain
outside default publication scope. Actual merge has its own explicitly authorized mode.
