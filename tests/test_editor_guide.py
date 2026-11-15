"""The step-by-step guide to the editor (docs/{en,pl}).

Every name of a button or field it shows exists in the editor's texts of that language, and every
picture it shows is in the repository, the same ones in both languages.
"""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUIDES = {"pl": ROOT / "docs/pl/przewodnik-edytora.html", "en": ROOT / "docs/en/editor-guide.html"}
I18N = ROOT / "custom_components/assist_router/www/editor/i18n.js"
TRANSLATIONS = ROOT / "custom_components/assist_router/translations"


class Guide(HTMLParser):
    """The names shown as the editor's (`<span class="ui">`) and the pictures of a page."""

    def __init__(self) -> None:
        super().__init__()
        self.names: list[str] = []
        self.pictures: list[str] = []
        self._depth = 0
        self._text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "img" and attributes.get("src", "").startswith("../assets/editor/"):
            self.pictures.append(attributes["src"])
        if tag == "span" and attributes.get("class") == "ui":
            self._depth, self._text = 1, ""
        elif self._depth:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        self._depth -= 1
        if not self._depth:
            self.names.append(" ".join(self._text.split()))

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._text += data


def read(language: str) -> Guide:
    guide = Guide()
    guide.feed(GUIDES[language].read_text(encoding="utf-8"))
    return guide


def texts(language: str) -> list[str]:
    """The texts of the editor in a language and the strings of the integration (its options)."""
    source = I18N.read_text(encoding="utf-8")
    start = source.index(f"\n  {language}: {{")
    block = source[start : source.index("\n  },", start)]
    entry = r'^\s{4}[a-z_0-9]+: "((?:[^"\\]|\\.)*)"'
    found = [json.loads(f'"{value}"') for value in re.findall(entry, block, re.M)]

    def strings(value: object) -> list[str]:
        if isinstance(value, dict):
            return [text for item in value.values() for text in strings(item)]
        return [value] if isinstance(value, str) else []

    found += strings(json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8")))
    return found


def as_pattern(text: str) -> re.Pattern[str]:
    """A text of the editor with its {placeholders} standing for anything."""
    parts = re.split(r"\{\w+\}", text)
    return re.compile(".+".join(re.escape(part) for part in parts) + r"\Z")


@pytest.mark.parametrize("language", ["pl", "en"])
def test_every_name_in_the_guide_is_on_the_screen(language: str) -> None:
    known = texts(language)
    patterns = [as_pattern(text) for text in known]
    names = read(language).names
    assert len(names) > 60
    # "+" is the button beside a group; a numbered step of the tester is its title with its number.
    missing = [
        name
        for name in names
        if name != "+"
        and name not in known
        and not any(pattern.match(name) for pattern in patterns)
        and re.sub(r"^\d+\. ", "", name) not in known
    ]
    assert missing == []


@pytest.mark.parametrize("language", ["pl", "en"])
def test_every_picture_is_there(language: str) -> None:
    pictures = read(language).pictures
    assert len(pictures) == 9
    for src in pictures:
        assert (GUIDES[language].parent / src).resolve().is_file(), src


def test_both_languages_show_the_same_steps() -> None:
    def names(language: str) -> list[str]:
        return [Path(src).name for src in read(language).pictures]

    assert names("pl") == names("en")
