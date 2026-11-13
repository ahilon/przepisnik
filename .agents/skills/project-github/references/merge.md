# Merge a specifically authorized PR

Enter only after the user explicitly authorizes merge of the identified PR in
the intended repository. Permission to prepare, commit, push or create a PR does
not include this operation.

- Use `gh` to verify the PR is open, not a draft, targets the intended base and
  still has the reviewed head SHA. Inspect current required checks, review decision,
  mergeability and branch-protection requirements; local success is insufficient.
- If required results are pending, missing or failed, reviews are unsatisfied,
  conflicts exist or the head changed after approval, stop and explain. Do not
  dismiss reviews, alter protection, rerun workflows or bypass checks to merge.
- Use the repository's permitted/agreed merge method. Include the inspected head
  with `gh pr merge --match-head-commit <sha>` so a racing push cannot silently
  change the merged content. Do not use `--admin` or enable auto-merge without
  separate authorization. If queued instead of completed, report that distinction.
- Re-read PR state and report the merge commit/SHA only when GitHub confirms it
  merged. Do not delete local/remote branches, pull, deploy or publish releases as
  an incidental cleanup. Those are separate actions or a later prepare operation.
