"""Build a fresh Respo recipe collection from explicitly assigned source folders."""

from pathlib import Path

from przepisnik.tools.respo import main

if __name__ == "__main__":
    raise SystemExit(main(project_root=Path(__file__).resolve().parents[2]))
