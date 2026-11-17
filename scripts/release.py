"""Command-line gates and publication of tested application images."""

import argparse
import json
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path

from scripts.image_registry import ImagePublisher, archive_image
from scripts.release_policy import PACKAGE_VERSION, ChangeDetector, verify_results


def package_version() -> str:
    """Read and validate the version from the checked-out project.

    Returns:
        str: A plain three-part application version.
    """
    with Path("pyproject.toml").open("rb") as source:
        version = tomllib.load(source)["project"]["version"]
    if not isinstance(version, str) or not PACKAGE_VERSION.fullmatch(version):
        raise ValueError("Image releases require a plain major.minor.patch version")
    return version


def append_output(path: Path | None, key: str, value: str) -> None:
    """Write a validated single-line value to GitHub's per-step output/env file.

    Args:
        path: Optional GitHub-owned output file.
        key: Fixed workflow output key.
        value: Validated value without line breaks.

    Returns:
        None: Appends one output when a destination was supplied.
    """
    if "\n" in value or "\r" in value:
        raise ValueError("Workflow output values must be single-line")
    if path is not None:
        with path.open("a", encoding="utf-8") as output:
            output.write(f"{key}={value}\n")
    return None


def main(argv: Sequence[str] | None = None) -> int:
    """Run one release gate, archive operation or already-authorized publication.

    Args:
        argv: Optional CLI arguments, otherwise read from the process.

    Returns:
        int: Zero for success or a stale candidate skip, one for an unsafe result.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("changes", "eligibility"):
        comparison = commands.add_parser(name)
        comparison.add_argument("--before", required=True)
        comparison.add_argument("--after", required=True)
        comparison.add_argument("--github-output", type=Path)
        if name == "changes":
            comparison.add_argument("--force", action="store_true")
    version = commands.add_parser("version")
    version.add_argument("--github-env", type=Path)
    results = commands.add_parser("verify-tests")
    results.add_argument("path", type=Path)
    archive = commands.add_parser("archive")
    archive.add_argument("--image", required=True)
    archive.add_argument("--architecture", required=True)
    archive.add_argument("--revision", required=True)
    archive.add_argument("--destination", type=Path, required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("--repository", required=True)
    publish.add_argument("--revision", required=True)
    publish.add_argument("--artifacts", type=Path, required=True)
    publish.add_argument("--candidate", required=True)
    args = parser.parse_args(argv)
    try:
        match args.command:
            case "changes":
                relevant = args.force or ChangeDetector().changed(args.before, args.after)
                append_output(args.github_output, "should_release", str(relevant).lower())
                print(json.dumps({"should_release": relevant}))
            case "eligibility":
                eligible = not ChangeDetector().changed(args.before, args.after)
                append_output(args.github_output, "eligible", str(eligible).lower())
                reason = "current runtime" if eligible else "superseded by newer code"
                print(json.dumps({"eligible": eligible, "reason": reason}))
            case "version":
                value = package_version()
                append_output(args.github_env, "PACKAGE_VERSION", value)
                print(value)
            case "verify-tests":
                verify_results(args.path)
            case "archive":
                archive_image(
                    args.image,
                    args.architecture,
                    args.revision,
                    package_version(),
                    args.destination,
                )
            case "publish":
                publisher = ImagePublisher(args.repository, args.revision, package_version())
                publisher.publish(args.artifacts, args.candidate)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
