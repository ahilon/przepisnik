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
| `project-github` | Verify finished work, prepare version/changelog and publish an authorized PR through Git/gh |
| `przepisnik` | Import recipes using the application CLI |
| `przepisnik-manage` | Browse/manage existing recipes using the application CLI |

The architect, developer and orchestrator skills are not installed yet. Their
planned workflow is sequential: agree on behavior, implement approved changes,
author approved tests, then verify/package through `project-github`. Do not treat
this roadmap as an existing autonomous agent system.

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

One approval of a concrete PR-publication phase covers branch creation, release
metadata, sync, checks, staging, commit, push, PR creation and CI inspection,
including refinements within the same agreed PR scope. Routine choices and the
next command do not need another conversational confirmation. The agent should
reuse saved, narrowly scoped host permissions and batch related operations where
appropriate. A sandbox escalation is a separate technical requirement, not a
request to approve the task again; skill instructions cannot disable it.

### Claude Code

Expose the same skill using the repository's existing per-skill link convention.
Create a link only if that path does not already exist; inspect an existing path
instead of replacing it.

```powershell
# Windows: one-time setup per clone, from the repository root
New-Item -ItemType Directory -Force .claude/skills | Out-Null
New-Item -ItemType Junction -Path .claude/skills/project-github -Target "$PWD/.agents/skills/project-github"
```

```bash
# macOS / Linux: one-time setup per clone
mkdir -p .claude/skills
ln -s ../../.agents/skills/project-github .claude/skills/project-github
```

Invoke `/project-github` with the same concrete scope and approval boundaries.
The machine-local link is ignored by Git. Recipe-skill links are documented in
[README.md](README.md#claude-code-and-codex-skills).

## What the GitHub skill does

1. Inspects the intended diff, base, repository, identity and existing branch/PR.
2. Creates/reuses a task branch such as `skill/github-pr-workflow`.
3. Updates `pyproject.toml`, a short changelog entry and the environment/lockfile.
4. Runs Ruff lint/format checks, Mypy, non-browser pytest with the CI coverage
   threshold, and Checkov. A failure stops publication; the skill does not silently
   rewrite application code/tests or weaken checks.
5. Commits only the agreed files, pushes the branch and creates/reuses a PR with
   `gh`. Reports the PR URL, version, SHA and local/remote verification status.

The exact verification commands live in the
[skill](.agents/skills/project-github/SKILL.md); committed workflows and tool
configuration take precedence when commands change. `scripts/check.cmd` is a
convenience command, not the whole PR verification suite.

Default local verification excludes browser E2E. Currently GitHub runs E2E on PRs
using an isolated Python server; they do not yet validate a built container. The
post-merge GHCR/stable pipeline is planned. Do not assume a PR or image is ready
because local non-browser checks passed. For manual E2E setup and execution, see
[tests/README.md](tests/README.md).

## Branches and versions

Branches use `<type>/<kebab-case-summary>`. Commit messages and PR titles use
`<type>(<optional-scope>): <summary>`. Types are `feat`, `fix`, `docs`, `skill`,
`workflow`, `test`, `refactor`, `perf`, `build` and `chore`.

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

Keep unrelated work out of the PR. Never use a blanket stage/reset/stash to solve
a dirty worktree. If unrelated edits affect validation, isolate the intended
candidate and ensure the evidence applies to its actual content before claiming
success.

Do not commit `local-artifacts/`, real recipe data, personal diet plans or
credentials. Tests use disposable fixtures. Repository skills must not perform
routine direct database edits; use the existing recipe skills/CLI instead.

Merge, auto-merge, GitHub releases, stable-tag promotion and production deployment
are outside the GitHub skill's default publication scope.
