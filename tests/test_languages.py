"""Language packs: completeness, selection and that the code reads the active pack."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import types

import pytest

from custom_components.assist_router import control, languages, voice
from custom_components.assist_router.languages import LANG, available_languages, check, pl
from custom_components.assist_router.router import parse_config

SOURCE = Path(__file__).parents[1] / "custom_components" / "assist_router"


@pytest.mark.parametrize("code", available_languages())
def test_every_name_used_by_the_code_is_in_the_pack(code: str) -> None:
    used = set()
    for path in SOURCE.glob("*.py"):
        used |= set(re.findall(r"\bLANG\.([A-Za-z_]\w*)", path.read_text(encoding="utf-8")))
    used -= {"code", "set"}  # methods of the LANG proxy itself
    missing = sorted(name for name in used if not hasattr(languages.PACKS[code], name))
    assert missing == []


@pytest.mark.parametrize("code", available_languages())
def test_every_pack_passes_the_checks(code: str) -> None:
    """Names, {fields}, Home Assistant names, JSON keys and every pattern example."""
    assert check.problems(languages.FOLDER / code) == []


def test_available_languages_and_selection() -> None:
    assert "pl" in available_languages()
    assert languages.set_language("pl-PL")
    assert LANG.code == "pl"
    assert not languages.set_language("xx")  # no pack - the current one stays
    assert LANG.code == "pl"


def test_a_pack_is_a_folder_of_data_and_grammar(tmp_path: Path) -> None:
    """A copy of the folder with a word translated is a working pack - the derived values follow."""
    folder = tmp_path / "xx"
    shutil.copytree(languages.FOLDER / "pl", folder)
    with (folder / "words.yaml").open("a", encoding="utf-8") as words:
        words.write("\nYES_WORDS: !tuple [ano, jo]\n")  # the later entry wins
    pack = languages.load_pack(folder, "test_pack_xx")
    assert pack.YES_WORDS == ("ano", "jo")
    assert pack.YES.match("ano, jasně") and not pack.YES.match("tak")  # built in grammar.py
    assert pack.OPEN_CLOSE["lock"]["HassTurnOn"][2] is pack.CLOSE_WORDS
    assert dict(pack.RELATIONS)["son"].search("mój syn")
    assert pack.PAST_DAYS[0][1] == 2


def test_the_checks_say_what_a_translator_broke(tmp_path: Path) -> None:
    folder = tmp_path / "xx"
    shutil.copytree(languages.FOLDER / "pl", folder)
    texts = (folder / "texts.yaml").read_text(encoding="utf-8")
    texts = re.sub(r"(?m)^(MORE_ITEMS: .*)\{count\}", r"\1{pocet}", texts)
    texts = re.sub(r"(?m)^NO_PRINTS: .*\n", "", texts)
    (folder / "texts.yaml").write_text(texts, encoding="utf-8")
    words = (folder / "words.yaml").read_text(encoding="utf-8")
    words = words.replace("  HassTurnOn: !tuple", "  ZapniIntent: !tuple", 1)
    (folder / "words.yaml").write_text(words, encoding="utf-8")
    patterns = (folder / "patterns.yaml").read_text(encoding="utf-8")
    patterns = patterns.replace(r"pattern: \b(h?alar|", r"pattern: \b(h?poplach|", 1)
    (folder / "patterns.yaml").write_text(patterns, encoding="utf-8")
    found = "\n".join(check.problems(folder))
    assert "missing: NO_PRINTS" in found
    assert "fields ['pocet'], expected ['count']" in found
    assert "INTENTS: keys are Home Assistant names" in found and "ZapniIntent" in found
    assert "ALARM_WORDS: does not recognize „włącz alarm”" in found
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "texts.yaml").write_text("A: [", encoding="utf-8")
    assert check.problems(broken)[0].startswith("the pack does not load")


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
