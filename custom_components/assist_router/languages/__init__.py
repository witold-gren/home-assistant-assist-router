"""Language packs: everything Assist Router says, recognizes or sends to the LLM in one language.

Each pack is a folder named after the language code (``pl/``) with four files - a new language
is a copy of the folder, translated (see "Adding a language" in the documentation):

- ``texts.yaml``: what Assist Router says and the prompts it sends to the LLM; ``{fields}`` are
  filled in by the code and stay as they are;
- ``words.yaml``: words and word lists used to understand commands and questions (yes / no,
  days, colors, verbs …) and the JSON keys the prompts ask for;
- ``patterns.yaml``: regular expressions, each with ``matches`` / ``not_matches`` examples that
  the tests check - so a translated pattern shows at once what it no longer recognizes;
- ``grammar.py``: the few functions that build sentences (they depend on grammar) and values
  derived from the data. It runs with every name of the YAML files already defined.

The YAML tags ``!tuple``, ``!set``, ``!frozenset`` and ``!translate`` keep the Python types the
code expects. The code uses the active pack through ``LANG`` (``LANG.YES_WORDS``,
``LANG.describe(...)``); the active pack is chosen once at setup (``set_language``). Every pack
is read once, when this module is imported (Home Assistant imports integrations outside its
event loop), so switching languages never touches the disk.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from types import ModuleType
from typing import Any

import yaml

DEFAULT_LANGUAGE = "pl"
FOLDER = Path(__file__).parent
DATA_FILES = ("texts.yaml", "words.yaml")
PATTERNS_FILE = "patterns.yaml"
GRAMMAR_FILE = "grammar.py"
FLAGS = {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE, "DOTALL": re.DOTALL}


class PackLoader(yaml.SafeLoader):
    """YAML of a language pack: ``!tuple``, ``!set``, ``!frozenset`` and ``!translate``."""


def _sequence(kind):
    def construct(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
        return kind(loader.construct_sequence(node, deep=True))

    return construct


def _translate(loader: yaml.SafeLoader, node: yaml.Node) -> dict[int, int]:
    """``{from: "ąć", to: "ac"}`` -> a str.translate table."""
    data = loader.construct_mapping(node)
    return str.maketrans(str(data["from"]), str(data["to"]))


PackLoader.add_constructor("!tuple", _sequence(tuple))
PackLoader.add_constructor("!set", _sequence(set))
PackLoader.add_constructor("!frozenset", _sequence(frozenset))
PackLoader.add_constructor("!translate", _translate)


def compile_pattern(spec: dict[str, Any]) -> re.Pattern[str]:
    flags = 0
    for name in spec.get("flags") or ():
        flags |= FLAGS[name]
    return re.compile(spec["pattern"], flags)


def build_pattern(spec: dict[str, Any]) -> Any:
    """One entry of patterns.yaml: a compiled pattern, or with ``items`` an ordered tuple of
    (key, pattern) or (pattern, value) pairs; ``compile: false`` keeps the patterns as text."""
    if "items" not in spec:
        return compile_pattern(spec)
    out = []
    for item in spec["items"]:
        pattern = compile_pattern(item) if spec.get("compile", True) else item["pattern"]
        out.append((item["key"], pattern) if "key" in item else (pattern, item["value"]))
    return tuple(out)


def pattern_examples(spec: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(label, single pattern spec) of an entry - one per item of a list."""
    if "items" not in spec:
        return [("", spec)]
    return [(str(item.get("key", item.get("value"))), item) for item in spec["items"]]


def read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=PackLoader)
    if data is not None and not isinstance(data, dict):
        raise ValueError(f"{path}: a mapping of names is expected")
    return data or {}


def load_pack(folder: Path, name: str) -> ModuleType:
    """The pack in ``folder`` as one module: the YAML names, then grammar.py run on top."""
    module = ModuleType(name)
    module.__file__ = str(folder / GRAMMAR_FILE)
    for file in DATA_FILES:
        module.__dict__.update(read_yaml(folder / file))
    patterns = read_yaml(folder / PATTERNS_FILE)
    module.__dict__["PATTERN_SPECS"] = patterns
    module.__dict__.update({key: build_pattern(spec) for key, spec in patterns.items()})
    grammar = folder / GRAMMAR_FILE
    if grammar.is_file():
        code = compile(grammar.read_text(encoding="utf-8"), str(grammar), "exec")
        exec(code, module.__dict__)
    return module


def _pack_folders() -> dict[str, Path]:
    return {
        path.name: path
        for path in sorted(FOLDER.iterdir())
        if path.is_dir() and not path.name.startswith("_") and (path / DATA_FILES[0]).is_file()
    }


def _load_all() -> dict[str, ModuleType]:
    packs = {}
    for code, folder in _pack_folders().items():
        pack = load_pack(folder, f"{__name__}.{code}")
        sys.modules[pack.__name__] = pack
        globals()[code] = pack  # `from .languages import pl` keeps working
        packs[code] = pack
    return packs


PACKS: dict[str, ModuleType] = _load_all()


def available_languages() -> list[str]:
    """Codes of the packs in this package, e.g. ["pl"]."""
    return sorted(PACKS)


def _base(language: str | None) -> str:
    return (language or "").replace("_", "-").split("-")[0].lower()


class _ActiveLanguage:
    """Forwards attribute access to the active pack module."""

    def __init__(self) -> None:
        self._pack: ModuleType = PACKS[DEFAULT_LANGUAGE]

    @property
    def code(self) -> str:
        return self._pack.__name__.rsplit(".", 1)[-1]

    def set(self, language: str | None) -> bool:
        """Activate the pack for ``language`` ("pl", "pl-PL"); False when there is none."""
        code = _base(language)
        if code not in PACKS:
            return False
        self._pack = PACKS[code]
        return True

    def __getattr__(self, name: str):
        return getattr(self._pack, name)


LANG = _ActiveLanguage()


def set_language(language: str | None) -> bool:
    """Activate a language pack; keeps the current one and returns False when missing."""
    return LANG.set(language)
