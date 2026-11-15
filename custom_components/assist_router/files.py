"""The router file on disk: read as text, and written with the previous content kept as .bak."""

from __future__ import annotations

from pathlib import Path
import shutil


def read_text(path: Path) -> str:
    """The text of a file, or nothing when it does not exist yet."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_with_backup(path: Path, text: str) -> None:
    """New file content; the previous one is kept alongside as .bak."""
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
