"""Language packs: completeness, selection and that the code reads the active pack."""

from __future__ import annotations

from pathlib import Path
import re
import types

import pytest

from custom_components.assist_router import control, languages, voice
from custom_components.assist_router.languages import LANG, available_languages, pl
from custom_components.assist_router.router import parse_config

SOURCE = Path(__file__).parents[1] / "custom_components" / "assist_router"


def test_every_name_used_by_the_code_is_in_the_pack() -> None:
    used = set()
    for path in SOURCE.glob("*.py"):
        used |= set(re.findall(r"\bLANG\.([A-Za-z_]\w*)", path.read_text(encoding="utf-8")))
    used -= {"code", "set"}  # methods of the LANG proxy itself
    missing = sorted(name for name in used if not hasattr(pl, name))
    assert missing == []


def test_available_languages_and_selection() -> None:
    assert available_languages() == ["pl"]
    assert languages.set_language("pl-PL")
    assert LANG.code == "pl"
    assert not languages.set_language("cs")  # no pack - the current one stays
    assert LANG.code == "pl"


def test_router_yaml_language_must_have_a_pack() -> None:
    topics = {"inne": {"description": "inne"}}
    assert parse_config({"language": "pl", "topics": topics}).topics
    with pytest.raises(ValueError, match="no language pack 'xx'"):
        parse_config({"language": "xx", "topics": topics})


@pytest.fixture
def test_pack(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """A copy of the Polish pack with a few replies changed, active for one test."""
    pack = types.ModuleType("custom_components.assist_router.languages.test")
    pack.__dict__.update({k: v for k, v in vars(pl).items() if not k.startswith("__")})
    pack.YES_WORDS = ("ano",)
    pack.YES = pl.words_pattern(pack.YES_WORDS)
    pack.ANSWER = pl.words_pattern(pack.YES_WORDS + pl.NO_WORDS)
    pack.NO_PRINTS = "No voiceprints yet."
    pack.done_speech = lambda intent_type, names, slots, domain=None: f"done {intent_type}"
    monkeypatch.setattr(LANG, "_pack", pack)
    return pack


def test_code_uses_the_active_pack(test_pack: types.ModuleType) -> None:
    assert control.answer_kind("ano") == "yes"
    assert control.answer_kind("tak") is None  # not a word of this pack
    assert control.is_bare_answer("ano")
    assert control.done_speech("HassTurnOn", ["lampa"], {}) == "done HassTurnOn"
    assert voice.NO_PRINTS == "No voiceprints yet."
