"""Questions are windows of the editor (ask.js), never window.confirm / alert / prompt."""

from __future__ import annotations

from pathlib import Path
import re

WWW = Path(__file__).resolve().parents[1] / "custom_components" / "assist_router" / "www"
NATIVE = re.compile(r"\b(?:window\.)?(confirm|alert|prompt)\s*\(")


def scripts() -> list[Path]:
    return sorted(path for path in WWW.rglob("*.js") if "vendor" not in path.parts)


def test_the_editor_scripts_are_found() -> None:
    names = {path.name for path in scripts()}
    assert {"editor-app.js", "sentences.js", "ask.js"} <= names


def test_no_native_browser_dialogs() -> None:
    found = []
    for path in scripts():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//", 1)[0]
            if NATIVE.search(code):
                found.append(f"{path.relative_to(WWW)}:{number}: {line.strip()}")
    assert found == [], "use ask() from www/editor/ask.js:\n" + "\n".join(found)
