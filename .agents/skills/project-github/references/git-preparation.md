# Prepare the task branch

This is authorized by an accepted implementation plan or an explicit GitHub
prepare/publish request. It is not a standing instruction to alter Git during
planning, review or status-only requests. Use the configured repository/base
(normally `origin` and `main`); verify them rather than assuming every clone agrees.

1. Inspect status, staged/unstaged/untracked paths, current branch, remotes,
   upstream and local commits. Stop for an ongoing merge/rebase, detached HEAD or
   ambiguous ownership. Inspect an existing stash list; never reuse another stash.
2. If the worktree is dirty and synchronization/switching is needed, create a
   uniquely named `git stash push --include-untracked` snapshot. Record its exact
   object ID, original branch, paths and staged state. Do not use `--all`: ignored
   personal data and environments must remain untouched. Stop before stashing
   suspected unignored credentials or private data. Verify the snapshot exists and
   the working tree/index is clean before moving on. If changes are mixed between
   unrelated tasks and cannot safely travel together, stop for scope/isolation.
3. Fetch the verified remote with pruning, then inspect branch existence and PR
   history through `gh`, checking head repository/branch and base. An open, closed
   unmerged and merged PR are distinct. Remote deletion alone is not proof of merge.
4. On the base branch, use `git pull --ff-only` for its configured upstream and
   verify local HEAD equals the fetched base. A local-ahead or diverged base is a
   blocker, not permission to reset, merge, rebase or push it.
5. On an active unmerged task branch, reuse it for the same task. Fast-forward its
   upstream if behind without local divergence. For an unpublished branch, verify
   its local commits belong to this task rather than treating it as deleted.
   Check the latest base is an ancestor; if integration requires a merge/rebase,
   explain the situation and obtain approval for that operation before proceeding.
6. If the current branch's PR was merged, preserve any local-only commits, switch
   to the base and perform step 4. If a published branch disappeared but merge is
   unconfirmed, or its PR closed without merge, stop and report the evidence. Do
   not abandon unpublished commits or recreate the deleted branch implicitly.
7. Once the base is verified current, create `<type>/<kebab-case-summary>` for a
   new task; never create a fresh task branch from stale/merged task history. An
   existing current branch for the same active task need not be recreated.
8. Restore only this operation's recorded stash onto the intended task branch
   with `git stash apply --index <recorded-id>`. Verify expected files and staged
   state. Use `apply`, not blind `pop`; keep the snapshot until restoration is
   confirmed. On conflicts or a failed synchronization, leave the snapshot intact,
   report the current branch/state and stop. Do not stage or publish conflicts.
9. After successful restoration, locate and drop only the exact snapshot created
   by this operation if its object ID still matches. Never clear the stash list or
   touch pre-existing stashes. If exact cleanup cannot be established, retain it
   and report the identifier rather than risk deleting another snapshot.

Final checks: intended branch/base, preserved task files, no unexpected staged
paths, restored stash state and base SHA. Any integration/restoration that changes
candidate content invalidates earlier verification. This procedure does not
authorize feature changes, commits, publication, branch deletion or force pushes.
