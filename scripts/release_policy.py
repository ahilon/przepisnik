"""Pure change and test-result policies for image publication."""

import json
import re
import tomllib
from pathlib import Path

from scripts.command_runner import CommandRunner

GIT_SHA = re.compile(r"[0-9a-f]{40}")
IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
PACKAGE_VERSION = re.compile(r"\d+\.\d+\.\d+")
RUNTIME_FILES = frozenset(
    {
        "docker/Dockerfile",
        "docker/entrypoint.sh",
        "docker/server.toml",
        "docker/demo/placeholder.png",
        ".dockerignore",
        ".github/workflows/release.yml",
    }
)


def affects_image(path: str, before: str | None = None, after: str | None = None) -> bool:
    """Classify image inputs, ignoring a project-version-only metadata bump.

    Args:
        path: Git-relative changed path.
        before: Previous metadata contents when the path is pyproject/lock.
        after: Candidate metadata contents, or None for a deletion.

    Returns:
        bool: Whether the changed path can affect the application or release checks.
    """
    if path.endswith(".md"):
        return False
    if path in {"pyproject.toml", "uv.lock"}:
        if before is None or after is None:
            return True
        return normalize_metadata(path, before) != normalize_metadata(path, after)
    return path in RUNTIME_FILES or path.startswith(("src/", "tests/", "scripts/"))


def normalize_metadata(path: str, contents: str) -> str:
    """Retain dependency/tool changes while excluding only the project's version.

    Args:
        path: pyproject.toml or uv.lock.
        contents: Valid TOML from one Git revision.

    Returns:
        str: Canonical metadata for comparison.
    """
    document = tomllib.loads(contents)
    if path == "pyproject.toml":
        document.get("project", {}).pop("version", None)
    else:
        for package in document.get("package", []):
            if package.get("source", {}).get("editable") == ".":
                package.pop("version", None)
    return json.dumps(document, sort_keys=True, default=str)


class ChangeDetector:
    """Compare real Git revisions rather than trusting PR labels or filenames alone."""

    def __init__(self) -> None:
        """Resolve the installed Git executable.

        Returns:
            None: Stores the shell-free command runner.
        """
        self._git = CommandRunner("git")
        return None

    def changed(self, before: str, after: str) -> bool:
        """Check all changed paths and semantic package metadata.

        Args:
            before: Full base commit SHA, or all zeroes for initial publication.
            after: Full candidate commit SHA.

        Returns:
            bool: True for relevant code/dependency/release changes.

        Raises:
            ValueError: If revisions are not full Git SHAs.
            subprocess.CalledProcessError: If required Git evidence is unavailable.
        """
        if not GIT_SHA.fullmatch(before) or not GIT_SHA.fullmatch(after):
            raise ValueError("Release comparisons require full Git commit SHAs")
        if set(before) == {"0"}:
            return True
        files = self._git.run(["diff", "--name-only", "-z", before, after]).stdout.split("\0")
        for path in filter(None, files):
            previous: str | None = None
            candidate: str | None = None
            if path in {"pyproject.toml", "uv.lock"}:
                previous = self._contents(before, path)
                candidate = self._contents(after, path)
            if affects_image(path, previous, candidate):
                return True
        return False

    def _contents(self, revision: str, path: str) -> str | None:
        """Read a metadata file only when it exists at the selected revision.

        Args:
            revision: Validated full commit SHA.
            path: One fixed metadata path selected by changed.

        Returns:
            str | None: File text or None for an absent file.
        """
        exists = self._git.run(["cat-file", "-e", f"{revision}:{path}"], check=False)
        if exists.returncode:
            return None
        return self._git.run(["show", f"{revision}:{path}"]).stdout


def verify_results(path: Path) -> None:
    """Require a positive collection with every selected test passed.

    Args:
        path: JSON produced by pytest's explicit release-results collector.

    Returns:
        None: All selected tests passed with no errors, skips or xfails/xpasses.

    Raises:
        ValueError: If results are missing, malformed or not a complete pass.
    """
    result = json.loads(path.read_text(encoding="utf-8"))
    required = {"collected", "passed", "failed", "skipped", "xfailed", "exit_code"}
    if not isinstance(result, dict) or set(result) != required:
        raise ValueError("Malformed release test summary")
    if any(type(value) is not int or value < 0 for value in result.values()):
        raise ValueError("Release test counts must be non-negative integers")
    if (
        result["collected"] <= 0
        or result["passed"] != result["collected"]
        or any(result[key] != 0 for key in ("failed", "skipped", "xfailed", "exit_code"))
    ):
        raise ValueError("Release requires every selected test to pass, with no skips or xfails")
    return None
