"""Language packs: everything Assist Router says, recognizes or sends to the LLM in one language.

Each pack is a module in this package named after the language code (``pl.py``). It holds
the spoken replies, the words and patterns used to understand commands and questions
(days, yes/no answers, verbs, colors...), the LLM prompts and the JSON keys the prompts ask
for, and a few functions that build sentences (they depend on grammar).

The code uses the active pack through ``LANG`` (``LANG.YES_WORDS``, ``LANG.describe(...)``),
so a new language is a new module with the same names - see "Adding a language" in the
documentation. The active pack is chosen once at setup (``set_language``).
"""

from __future__ import annotations

from importlib import import_module
import pkgutil
from types import ModuleType

DEFAULT_LANGUAGE = "pl"


def available_languages() -> list[str]:
    """Codes of the packs in this package, e.g. ["pl"]."""
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if not m.name.startswith("_"))


def _base(language: str | None) -> str:
    return (language or "").replace("_", "-").split("-")[0].lower()


class _ActiveLanguage:
    """Forwards attribute access to the active pack module."""

    def __init__(self) -> None:
        self._pack: ModuleType = import_module(f"{__name__}.{DEFAULT_LANGUAGE}")

    @property
    def code(self) -> str:
        return self._pack.__name__.rsplit(".", 1)[-1]

    def set(self, language: str | None) -> bool:
        """Activate the pack for ``language`` ("pl", "pl-PL"); False when there is none."""
        code = _base(language)
        if code not in available_languages():
            return False
        self._pack = import_module(f"{__name__}.{code}")
        return True

    def __getattr__(self, name: str):
        return getattr(self._pack, name)


LANG = _ActiveLanguage()


def set_language(language: str | None) -> bool:
    """Activate a language pack; keeps the current one and returns False when missing."""
    return LANG.set(language)
