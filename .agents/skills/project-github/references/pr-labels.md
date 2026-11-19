# Pull request labels

Apply the primary label from the Conventional Commit type in the PR title,
including titles with a scope or breaking-change marker. Keep the branch and
PR title aligned with the actual change. This happens through gh during an
already-authorized PR publication or update; it adds no Actions workflow/check.

| PR type | Label |
| --- | --- |
| `fix` | `bug` |
| `skill` | `agent` |
| `test` or `tests` | `tests` |
| `feat` | `feature` |
| `docs` | `docs` |
| `chore` | `maintenance` |
| `workflow` | `workflow` |
| `build` | `build` |

`test` remains the canonical branch/commit type; `tests` is accepted as a label
mapping alias. Types not listed here have no automatic primary label. Preserve
existing labels and do not invent mappings or substitute `documentation` for
`docs`, or `enhancement` for `feature`.

Before publication, inspect `gh label list` and reuse the exact repository label.
If a mapped label is missing, creating that exact label is part of the approved
labelled publication; leave existing label names/colors/descriptions intact.
Do not add labels retroactively to unrelated PRs.

For a new PR, append `--label <mapped-label>` to the normal `gh pr create`
command with its prepared `--body-file`. Omit this flag for an unmapped type.
For an existing PR, add the expected label without removing other labels:

```text
gh pr edit <number> --add-label <mapped-label>
```

Repeated publication attempts must reuse the PR and its labels. Verify the
result with `gh pr view <number> --json url,labels,headRefOid` and report the
applied label with the publication result. Do not claim a label was applied
based only on a command's intention.

## Closed pull requests

The separate `.github/workflows/pr-status-labels.yml` automation manages only the
`rejected` status label. A closed, unmerged PR receives it; a reopened or merged
PR has it removed. Existing type/topic labels remain intact.

The workflow runs only on close/reopen events, reads current PR metadata instead
of trusting an old event state and never checks out or executes PR code. It is
not a merge gate. It starts handling future events once installed on the default
branch; historical closed PRs are not backfilled by this workflow.
