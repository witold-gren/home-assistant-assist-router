"""MkDocs hook of the documentation site (mkdocs.yml).

Before each build, pages kept elsewhere in the repository are written into docs/ (only when they
changed, so `mkdocs serve` does not rebuild in a loop; the copies are not kept in git):

- the changelog (CHANGELOG.md), shown in both languages;
- the guide from scratch (GUIDE.md, PRZEWODNIK.md), which GitHub shows at the top of the repository:
  its chapters get the same anchors in both languages, links to files of the repository go to GitHub
  and links to the old documentation site go to the pages of this one.

After the build, the addresses of the old hand-written site (en/, en/editor-guide.html,
pl/modele.html, ...) lead to the new pages, anchors included: the editor's "?" of released
versions opens them.
"""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
GITHUB = "https://github.com/witold-gren/home-assistant-assist-router/blob/main/"
OLD_SITE = "https://witold-gren.github.io/home-assistant-assist-router/"

GUIDES = {"guide.md": "GUIDE.md", "guide.pl.md": "PRZEWODNIK.md"}
CHANGELOGS = {"changelog.md": "CHANGELOG.md", "changelog.pl.md": "CHANGELOG.md"}
# The chapters of the guide from scratch, by their number; the last one has none.
GUIDE_ANCHORS = (
    "how",
    "home-assistant",
    "speech",
    "ollama",
    "assist-router",
    "pipelines",
    "speaker-id",
    "automations",
    "problems",
    "privacy",
)
GUIDE_MAP_ANCHOR = "map"

# The old hand-written site: page -> {old anchor -> new page/#anchor}; "" is the page itself.
_INDEX = {
    "": "",
    "co": "#what",
    "what": "#what",
    "jak": "#how",
    "how": "#how",
    "wymagania": "installation/#requirements",
    "requirements": "installation/#requirements",
    "instalacja": "installation/#installation",
    "installation": "installation/#installation",
    "opcje": "installation/#options",
    "options": "installation/#options",
    "przyklady": "installation/#examples",
    "examples": "installation/#examples",
    "edytor": "editor/#editor",
    "editor": "editor/#editor",
    "edytor-faq": "faq/#editor-faq",
    "editor-faq": "faq/#editor-faq",
    "router": "router-yaml/#router",
    "nowy": "router-yaml/#new-topic",
    "new-topic": "router-yaml/#new-topic",
    "przyklad": "router-yaml/#example",
    "example": "router-yaml/#example",
    "dane": "data/#data",
    "data": "data/#data",
    "mowca": "data/#speaker",
    "speaker": "data/#speaker",
    "postacie": "data/#personas",
    "personas": "data/#personas",
    "sterowanie": "control/",
    "control": "control/",
    "dziennik": "good-practice/#log",
    "log": "good-practice/#log",
    "test": "good-practice/#testing",
    "testing": "good-practice/#testing",
    "douczanie": "good-practice/#fine-tuning",
    "fine-tuning": "good-practice/#fine-tuning",
    "prywatnosc": "privacy/",
    "privacy": "privacy/",
    "jezyk": "languages/",
    "adding-a-language": "languages/",
}
_EDITOR = {
    "": "editor/",
    "zanim": "editor/#before",
    "before": "editor/#before",
    "ekran": "editor/#screen",
    "screen": "editor/#screen",
    "nauka": "editor/#learning",
    "learning": "editor/#learning",
    "temat": "editor/#topic",
    "topic": "editor/#topic",
    "dane": "editor/#data",
    "data": "editor/#data",
    "tester": "editor/#tester",
    "testy": "editor/#tests",
    "tests": "editor/#tests",
    "zapis": "editor/#save",
    "save": "editor/#save",
    "historia": "editor/#history",
    "history": "editor/#history",
    "komenda": "editor/#command",
    "command": "editor/#command",
    "problemy": "faq/#problems",
    "problems": "faq/#problems",
}
_MODELS = {
    "": "models/",
    "test": "models/#tested",
    "tested": "models/#tested",
    "wyniki": "models/#results",
    "results": "models/#results",
    "wnioski": "models/#conclusions",
    "conclusions": "models/#conclusions",
    "bledy": "models/#errors",
    "errors": "models/#errors",
    "douczanie": "models/#fine-tuning",
    "fine-tuning": "models/#fine-tuning",
    "powtorz": "models/#repeat",
    "repeat": "models/#repeat",
}
OLD_PAGES = {
    "en/index.html": ("en", _INDEX),
    "en/editor-guide.html": ("en", _EDITOR),
    "en/models.html": ("en", _MODELS),
    "pl/index.html": ("pl", _INDEX),
    "pl/przewodnik-edytora.html": ("pl", _EDITOR),
    "pl/modele.html": ("pl", _MODELS),
}
_OLD_FILES = {"": "index.html"} | {
    name: name
    for name in (
        "index.html",
        "editor-guide.html",
        "models.html",
        "przewodnik-edytora.html",
        "modele.html",
    )
}


def new_place(old_page: str, anchor: str = "") -> str:
    """The page (and anchor) of the new site, relative to the language root, for an old address."""
    _, table = OLD_PAGES[old_page]
    return table.get(anchor, table[""])


def _page_link(target: str) -> str:
    """A place of the new site ("data/#speaker", "#how", "") as a link to the page source."""
    page, _, anchor = target.partition("#")
    page = page.strip("/") or "index"
    return f"{page}.md" + (f"#{anchor}" if anchor else "")


def guide_page(text: str) -> str:
    """GUIDE.md / PRZEWODNIK.md as a page of the site."""
    switch = (
        r"\[English\]\(GUIDE\.md\) · \*\*Polski\*\*|\*\*English\*\* · \[Polski\]\(PRZEWODNIK\.md\)"
    )
    text = re.sub(rf"^({switch})\n+", "", text, flags=re.M)

    def chapter(match: re.Match[str]) -> str:
        number, title = match.group(1), match.group(2)
        return f"## {title} {{#{GUIDE_ANCHORS[int(number)]}}}"

    text = re.sub(r"^## (\d+)\. (.+)$", chapter, text, flags=re.M)
    text = re.sub(
        r"^## ((?:Mapa dokumentacji|Documentation map))$",
        rf"## \1 {{#{GUIDE_MAP_ANCHOR}}}",
        text,
        flags=re.M,
    )

    def link(match: re.Match[str]) -> str:
        label, href = match.group(1), match.group(2)
        if href.startswith(OLD_SITE):
            rest = href[len(OLD_SITE) :]
            lang, _, rest = rest.partition("/")
            path, _, anchor = rest.partition("#")
            return f"[{label}]({_page_link(new_place(f'{lang}/{_OLD_FILES[path]}', anchor))})"
        if href.startswith(("http", "#", "mailto")):
            return match.group(0)
        if href in ("CHANGELOG.md",):
            return f"[{label}](changelog.md)"
        return f"[{label}]({GITHUB}{href})"

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)


def generated_pages() -> dict[str, str]:
    """The pages written into docs/ before a build: file name -> text."""
    pages = {
        name: (ROOT / source).read_text(encoding="utf-8") for name, source in CHANGELOGS.items()
    }
    pages |= {
        name: guide_page((ROOT / source).read_text(encoding="utf-8"))
        for name, source in GUIDES.items()
    }
    return pages


def on_pre_build(config, **kwargs) -> None:
    for name, text in generated_pages().items():
        path = ROOT / "docs" / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")


REDIRECT = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><title>Assist Router</title>
<meta name="robots" content="noindex">
<script>
var places = {places};
var place = places[location.hash.slice(1)] || places[""];
location.replace("{root}" + place);
</script>
<meta http-equiv="refresh" content="0; url={root}{default}">
</head><body><a href="{root}{default}">Assist Router</a></body></html>
"""
# The old Polish start page was pl/ - now the Polish start of this site: its old anchors move on.
OLD_ANCHORS_SCRIPT = """<script>
(function () {{
  var places = {places};
  var place = places[location.hash.slice(1)];
  if (place && place.charAt(0) !== "#") location.replace("{root}" + place);
}})();
</script>
"""


def on_post_build(config, **kwargs) -> None:
    import json

    site = Path(config["site_dir"])
    for old, (lang, table) in OLD_PAGES.items():
        root = "../" if lang == "en" else ""
        places = json.dumps(table, ensure_ascii=False)
        path = site / old
        if old == "pl/index.html":
            if not path.is_file():
                continue
            # the Polish start page itself: only its old anchors are sent on
            page = path.read_text(encoding="utf-8")
            script = OLD_ANCHORS_SCRIPT.format(places=places, root="")
            if script not in page:
                path.write_text(page.replace("</head>", script + "</head>", 1), encoding="utf-8")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            REDIRECT.format(lang=lang, places=places, root=root, default=table[""]),
            encoding="utf-8",
        )
