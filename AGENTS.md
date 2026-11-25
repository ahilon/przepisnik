# Shared project workflow

Use these rules in Codex and Claude Code. Canonical procedures live in
`.agents/skills/`; Claude entry points only reference those files.

- Use `project-lead` for project discussion, architecture and phase coordination.
  Planning is read-only behavior: present the plan in conversation and wait for
  approval before implementation. Current host permissions are unchanged; this
  agreement is not a separate filesystem sandbox.
- After plan approval, use `project-github` in prepare mode to synchronize the
  task branch, then `project-developer` in implement mode. Do not write/run tests
  during implementation unless the user explicitly authorized a broader phase.
- When the user declares the implementation ready and requests tests, use
  `project-developer` in tests mode, then `project-tester`. That test-phase request
  covers authoring and verification unless the user explicitly limits it.
- Report verification results and readiness; obtain approval for GitHub publication.
  PR creation and actual merge are separate operations. Never infer permission to
  merge from approval to push or open a PR.
- One approval covers the agreed phase and routine repairs within its scope.
  Reuse it; ask only at an unapproved phase boundary or for a material new decision.
  Host permission prompts remain distinct. Follow an explicitly narrower request.
- Run roles sequentially in the current session by default. Load the next skill
  explicitly and announce the handoff. Use separate agents only when requested or
  specifically authorized; never claim a handoff created an independent process.
- Apply `.agents/skills/project-developer/references/python-style.md` when writing
  Python. Do not add a new direct dependency without approval.
- Preserve unrelated work and personal recipe data. Only the GitHub preparation
  procedure may perform the authorized named-stash/sync/restore sequence; other
  roles must not automatically stash/reset/rebase. No force push or destructive
  cleanup without explicit authorization.
- Use `project-notes` to save or recall project knowledge in Obsidian. At session
  wrap-up or an agreed project milestone, offer a handoff once; write it on request.
- Use `przepisnik` / `przepisnik-manage` for recipe operations, not direct database
  edits. Keep personal data, credentials and `local-artifacts/` out of commits.

Read `DEVELOPING.md` for setup and invocation examples, and `tests/README.md` when
changing test fixtures. `.agents/commit.md` is a compatibility pointer, not another
policy. Do not load the whole documentation tree for every task.
