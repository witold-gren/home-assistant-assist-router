"""The documentation site (docs/, mkdocs.yml).

Both languages have the same pages, the same anchors and the same pictures; every link and
picture exists; every name of a button or field (`<b class="ui">`) is on the editor's screen
or in the integration's options; the old addresses of the hand-written site lead on; the site
builds with `mkdocs build --strict` in Docker (make test-docker).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
I18N = ROOT / "custom_components/assist_router/www/editor/i18n.js"
TRANSLATIONS = ROOT / "custom_components/assist_router/translations"

_spec = importlib.util.spec_from_file_location("docs_site", ROOT / "dev/docs_site.py")
docs_site = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(docs_site)


def pages(language: str) -> dict[str, str]:
    """name (without .pl) -> text, the pages written by hand and those the hook writes."""
    generated = docs_site.generated_pages()
    found = {}
    for path in sorted(DOCS.glob("*.md")):
        polish = path.name.endswith(".pl.md")
        if polish != (language == "pl") or path.name in generated:
            continue
        found[path.name.removesuffix(".pl.md").removesuffix(".md")] = path.read_text(
            encoding="utf-8"
        )
    for name, text in generated.items():
        if name.endswith(".pl.md") == (language == "pl"):
            found[name.removesuffix(".pl.md").removesuffix(".md")] = text
    return found


def without_code(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.S)


def anchors(text: str) -> list[str]:
    return re.findall(r"^#+ .*\{#([a-z0-9-]+)\}\s*$", without_code(text), re.M)


def headings(text: str) -> list[str]:
    return re.findall(r"^#{2,3} .*$", without_code(text), re.M)


def pictures(text: str) -> list[str]:
    return re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text)


def ui_names(text: str) -> list[str]:
    return [" ".join(name.split()) for name in re.findall(r'<b class="ui">(.*?)</b>', text, re.S)]


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


def test_both_languages_have_the_same_pages() -> None:
    assert set(pages("pl")) == set(pages("en"))
    assert {
        "index",
        "installation",
        "editor",
        "router-yaml",
        "good-practice",
        "models",
        "faq",
        "changelog",
    } <= set(pages("en"))


def test_the_navigation_lists_every_page() -> None:
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    listed = set(re.findall(r"^  - [^:]+: ([a-z-]+)\.md$", config, re.M))
    assert listed == set(pages("en"))


@pytest.mark.parametrize("name", sorted(pages("en")))
def test_both_languages_have_the_same_anchors_and_sections(name: str) -> None:
    english, polish = pages("en")[name], pages("pl")[name]
    assert anchors(english) == anchors(polish)
    if name != "changelog":
        assert len(headings(english)) == len(headings(polish))


@pytest.mark.parametrize("name", sorted(set(pages("en")) - {"changelog"}))
def test_every_heading_has_an_anchor(name: str) -> None:
    for language in ("pl", "en"):
        bare = [line for line in headings(pages(language)[name]) if "{#" not in line]
        assert bare == [], (language, name)


def test_the_anchors_of_a_page_are_unique() -> None:
    for language in ("pl", "en"):
        for name, text in pages(language).items():
            found = anchors(text)
            assert len(found) == len(set(found)), (language, name)


@pytest.mark.parametrize("language", ["pl", "en"])
def test_every_local_link_and_picture_exists(language: str) -> None:
    known = pages(language)
    for name, text in known.items():
        for href in re.findall(r"\]\(([^)\s]+)\)", without_code(text)):
            if href.startswith(("http", "mailto")):
                continue
            path, _, anchor = href.partition("#")
            if path.startswith("assets/"):
                assert (DOCS / path).is_file(), (name, href)
                continue
            target = name if not path else path.removesuffix(".md")
            assert target in known, (name, href)
            if anchor:
                assert anchor in anchors(known[target]), (name, href)


def test_both_languages_show_the_same_pictures() -> None:
    def names(language: str) -> list[str]:
        return [Path(src).name for text in pages(language).values() for src in pictures(text)]

    assert names("pl") == names("en")
    assert len(names("en")) >= 9
    for language in ("pl", "en"):
        for text in pages(language).values():
            for src in pictures(text):
                assert f"/screens/{language}/" in src or "/screens/" not in src, src


@pytest.mark.parametrize("language", ["pl", "en"])
def test_every_name_in_the_docs_is_on_the_screen(language: str) -> None:
    known = texts(language)
    patterns = [as_pattern(text) for text in known]
    names = [name for text in pages(language).values() for name in ui_names(text)]
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


def test_the_editor_views_have_their_chapters() -> None:
    """The anchors the editor's "?" links point at (docs/editor.md and its Polish twin)."""
    editor = anchors(pages("en")["editor"])
    for view in (
        "before",
        "screen",
        "learning",
        "topic",
        "data",
        "tester",
        "tests",
        "save",
        "history",
        "command",
    ):
        assert view in editor


def test_the_old_addresses_lead_to_existing_places() -> None:
    known = pages("en")
    for table in (docs_site._INDEX, docs_site._EDITOR, docs_site._MODELS):
        for place in table.values():
            page, _, anchor = place.partition("#")
            page = page.strip("/") or "index"
            assert page in known, place
            if anchor:
                assert anchor in anchors(known[page]), place


def test_the_guide_from_scratch_gets_anchors_and_site_links() -> None:
    for name in ("guide.md", "guide.pl.md"):
        text = docs_site.generated_pages()[name]
        assert docs_site.OLD_SITE not in text
        assert "](GUIDE.md)" not in text and "](PRZEWODNIK.md)" not in text
        assert anchors(text) == [*docs_site.GUIDE_ANCHORS, docs_site.GUIDE_MAP_ANCHOR]


def test_the_design_folder_is_left_out_of_the_site() -> None:
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert re.search(r"^exclude_docs: \|\n  /design/$", config, re.M)


def docker_runs() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


@pytest.mark.docker
@pytest.mark.skipif(not docker_runs(), reason="Docker is not running here")
def test_the_site_builds_strictly(tmp_path: Path) -> None:
    # As make docs-build does: the docs-site stage of the Dockerfile, strict.
    site = tmp_path / "site"
    output = ["--output", f"type=local,dest={site}", "."]
    result = subprocess.run(
        ["docker", "build", "-q", "-f", "dev/docker/Dockerfile", "--target", "docs-site", *output],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    assert (site / "pl/editor/index.html").is_file()
    assert (site / "editor/index.html").is_file()
    assert "editor/#screen" in (site / "pl/przewodnik-edytora.html").read_text(encoding="utf-8")
    assert "places" in (site / "pl/index.html").read_text(encoding="utf-8")


EDITOR_ANCHORS = ROOT / "custom_components" / "assist_router" / "www" / "editor" / "docs-anchors.js"


def test_every_question_mark_of_the_editor_opens_a_chapter_that_is_there() -> None:
    table = re.search(
        r"DOCS_ANCHORS = \{(.+?)\};", EDITOR_ANCHORS.read_text(encoding="utf-8"), re.S
    ).group(1)
    wanted = set(re.findall(r'^\s+\w+: "([\w-]+)",$', table, re.M))
    assert wanted
    for name in ("editor.md", "editor.pl.md"):
        anchors = set(
            re.findall(r"\{#([\w-]+)\}", (ROOT / "docs" / name).read_text(encoding="utf-8"))
        )
        assert wanted <= anchors, name


def test_no_name_of_the_screen_is_left_as_a_span() -> None:
    """Names are <b class="ui">: bold on GitHub too, which drops the class of a <span>."""
    pages = (ROOT / "docs").rglob("*.md")
    leftovers = [
        page.name for page in pages if '<span class="ui">' in page.read_text(encoding="utf-8")
    ]
    assert not leftovers
