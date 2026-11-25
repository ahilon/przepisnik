"""Locate the Obsidian project vault and update an individual Polish note."""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

if sys.platform == "win32":
    import winreg

ROOT_SETTING = "RAG_Path"
NOTES = ("Plan projektu.md", "Pomysły.md", "Decyzje.md", "Raspberry Pi.md", "Przekazanie sesji.md")


def locate() -> Path:
    """Resolve the configured vault afresh, including persisted Windows user settings."""
    parent = os.environ.get(ROOT_SETTING, "").strip()
    if not parent and sys.platform == "win32":
        with (
            suppress(FileNotFoundError),
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key,
        ):
            value, kind = winreg.QueryValueEx(key, ROOT_SETTING)
            if isinstance(value, str):
                parent = os.path.expandvars(value) if kind == winreg.REG_EXPAND_SZ else value
    if not parent or not Path(parent).is_absolute():
        raise ValueError("Set RAG_Path to the absolute parent directory of the vault.")
    vault = Path(parent) / "przepisnik"
    if not (vault / ".obsidian").is_dir():
        raise ValueError(f"Expected an existing Obsidian vault at {vault}.")
    return vault.resolve(strict=True)


def snapshot(target: Path) -> tuple[str, str]:
    """Read the note and revision from the same bytes, or report a missing note."""
    if target.is_symlink() or target.is_junction():
        raise ValueError(f"Expected a regular note file at {target}.")
    try:
        content = target.read_bytes()
    except FileNotFoundError:
        return "missing", ""
    return hashlib.sha256(content).hexdigest(), content.decode("utf-8-sig")


def save(target: Path, expected: str, text: str) -> None:
    """Replace an observed note atomically; preserve stale or unchanged content."""
    revision, previous = snapshot(target)
    if revision != expected:
        raise ValueError(f"Note changed; reread {target} before saving.")
    if not text.strip():
        raise ValueError("Supply nonempty Markdown.")
    if text == previous:
        return None
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as file:
        temp = Path(file.name)
    try:
        temp.write_bytes(text.encode("utf-8"))
        if expected == "missing":
            # Publish only if the destination still does not exist.
            os.link(temp, target)
        else:
            if snapshot(target)[0] != expected:
                raise ValueError(f"Note changed; reread {target} before saving.")
            temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return None


def main() -> None:
    """Print a vault path or JSON snapshot; save a UTF-8 input file on explicit request."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--note", choices=NOTES)
    parser.add_argument("--expected")
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    vault = locate()
    if (args.expected is None) != (args.input is None) or (args.input and not args.note):
        parser.error("A write requires --note, --expected and --input.")
    if args.note is None:
        sys.stdout.write(f"{vault}\n")
        return None
    target = vault / args.note
    if args.input is None:
        revision, text = snapshot(target)
        sys.stdout.write(json.dumps({"path": str(target), "hash": revision, "text": text}) + "\n")
    else:
        save(target, args.expected, args.input.read_bytes().decode("utf-8-sig"))
        sys.stdout.write(f"{target}\n")
    return None


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"Project notes: {error}")
