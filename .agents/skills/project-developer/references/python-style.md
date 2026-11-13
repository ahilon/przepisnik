# Python implementation conventions

Apply these rules to new or materially changed code, including authored tests.
Keep edits focused; do not rewrite unrelated modules to enforce them globally.

## Dependencies

- Prefer Python's standard library when it meets the task clearly and efficiently.
- Existing direct dependencies in `pyproject.toml` may be used in their declared
  context. Development-only packages must not become undeclared runtime imports.
- Ask before introducing a direct dependency, even when installed or present
  transitively in `uv.lock`. Explain the concrete readability/performance benefit,
  dependency/image cost and simpler alternative. Do not assume NumPy is justified
  for small collections or claim performance gains without evidence.

## Classes, names and responsibility

- Default to classes for new application components and cohesive behavior/state.
  Use descriptive class and method names that identify their domain purpose.
  Do not create empty wrappers or force a class around an existing pure utility
  solely for style; preserve the design of untouched APIs and framework callbacks.
- Give each method one clear responsibility. Extract a private `_helper` when it
  names a meaningful unit of logic, reduces duplication or keeps the main method
  understandable. Avoid a chain of trivial one-line helpers.
- Keep branching shallow through guard clauses, validation helpers or dispatch
  where appropriate. Do not hide complex branching inside comprehensions.
- Store stable object-owned state on the instance. Use `@property` for cheap,
  side-effect-free access to derived/validated object state; do not use it merely
  to avoid passing arguments. Keep per-call inputs local and avoid mutable
  per-operation state that can leak between requests or concurrent calls.

## Expressions, returns and constants

- Prefer list comprehensions for simple collection transformations/filters.
  Use a generator for lazy consumption, and a normal loop for complex branching,
  exception handling or side effects. Do not create a list just for side effects.
- Split dense calculations into a few variables with meaningful domain names.
  Avoid both a single tangled multiline expression and unnecessary intermediates
  for every obvious operation.
- Use `return None`, not a bare `return`, when intentionally returning no value.
  For `-> None` methods, make normal completion explicit with `return None` where
  compatible with the framework contract. Do not add value returns to generators,
  abstract stubs or callbacks where they would change semantics.
- Replace unexplained domain numbers and repeated semantic strings with named
  `UPPER_SNAKE_CASE` constants, optionally annotated with `Final` when useful.
  Ordinary structural literals such as an empty list or a zero-based index do not
  automatically require constants.
- Keep constants at the narrowest useful scope: private/module constants for one
  module; shared domain constants in the appropriate shared module. Avoid a
  global constants dumping ground or duplicated sources of truth. Configurable
  values belong in configuration; secrets never belong in committed constants.

## Types and Google-style docstrings

- Annotate every new/modified function and method's parameters and return type,
  including `__init__(...) -> None`. Do not annotate `self`/`cls` unnecessarily.
- Type class/instance attributes and local variables where inference is ambiguous
  or a domain/container type needs clarification. Do not repeat obvious types on
  every literal assignment. Prefer specific domain types over unqualified `Any`.
- Document every new/modified class, method and function, including private helpers
  and constructors. Use a concise purpose summary and Google-style `Args`,
  `Returns`, and `Raises` sections when applicable; use `Yields` for generators.
  Describe meaning, units, constraints and behavior rather than repeating names.
- Parameter types are required in signatures. When useful, include types in the
  Google docstring as well; keep them consistent with the annotations. Document
  `None` explicitly for methods that return no result. Omit an empty `Args` section
  for an argument-free method, and do not list `self` as a public argument.
- Class docstrings describe responsibility and relevant public attributes;
  constructor docstrings explain initialization arguments. Follow the repository's
  `[tool.ruff.lint.pydocstyle] convention = "google"`, not a mixed `:param` format.

Example method within an existing class:

```python
def update_label(self, label: str) -> None:
    """Replace the label displayed in the summary.

    Args:
        label (str): Non-empty text for the summary heading.

    Returns:
        None: The label is stored on this instance.

    Raises:
        ValueError: If the label contains no visible characters.
    """
    normalized_label = label.strip()
    if not normalized_label:
        raise ValueError("Label must not be empty")
    self._label = normalized_label
    return None
```
