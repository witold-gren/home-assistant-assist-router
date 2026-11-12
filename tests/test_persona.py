"""Personas: who the assistant is in an Assist pipeline (router.yaml ``personas``)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.assist_router import conversation as agent_module
from custom_components.assist_router.languages import pl
from custom_components.assist_router.router import (
    answer_messages,
    find_persona,
    parse_config,
    summary_messages,
)

from .conftest import AGENT_ID

TOPICS = {"inne": {"description": "wszystko inne"}}
PERSONAS = {
    "jarvis": {
        "pipelines": "Hej Jarvis",
        "gender": "male",
        "prompt": "Jesteś Jarvisem, superinteligentnym systemem z Iron Mana.",
    },
    "elza": {
        "pipelines": ["01elza"],
        "voices": ["pl_PL-elza-medium"],
        "gender": "female",
        "prompt": "Jesteś Elzą,\n  królową z bajki Kraina lodu.",
    },
    "optimus": {"voices": "pl_PL-optimus-medium", "prompt": "Jesteś Optimusem Prime."},
}


def _config(personas=PERSONAS):
    return parse_config({"topics": TOPICS, "personas": personas})


def test_personas_are_parsed() -> None:
    config = _config()
    elza = next(p for p in config.personas if p.name == "elza")
    assert elza.prompt == "Jesteś Elzą, królową z bajki Kraina lodu."  # one line
    assert elza.voices == ("pl_pl-elza-medium",) and elza.gender == "female"
    assert config.personas[0].pipelines == ("hej jarvis",)
    assert config.personas[2].gender is None
    assert parse_config({"topics": TOPICS}).personas == ()


@pytest.mark.parametrize(
    ("personas", "error"),
    [
        ({"x": {"pipelines": "a"}}, "prompt is missing"),
        ({"x": {"pipelines": "a", "prompt": "p", "gender": "she"}}, "male or female"),
        ({"x": {"prompt": "p"}}, "give pipelines or voices"),
        (["x"], "a map of names"),
    ],
)
def test_invalid_personas(personas, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        _config(personas)


@pytest.mark.parametrize(
    ("pipeline_id", "name", "voice", "expected"),
    [
        ("01a", "Pokój Jana Hej Jarvis", "pl_PL-vision", "jarvis"),  # a name fragment
        ("01elza", "Pokój Dziewczyn", None, "elza"),  # the pipeline id
        ("01b", "Pokój Jana Hej Jarvis", "pl_PL-Elza-medium", "elza"),  # the voice wins
        ("01c", "Salon", "pl_PL-optimus-medium", "optimus"),
        ("01d", "Salon OK Nabu", "pl_PL-vision", None),
        ("01e", None, None, None),
    ],
)
def test_find_persona(pipeline_id, name, voice, expected) -> None:
    persona = find_persona(_config(), pipeline_id, name, voice)
    assert (persona.name if persona else None) == expected


def test_prompts_get_the_persona_only_when_there_is_one() -> None:
    config = _config()
    jarvis = config.personas[0]
    now = datetime(2026, 11, 8, 10, 0)
    plain = answer_messages(config, now, "dane", "ile?")[0]["content"]
    with_persona = answer_messages(config, now, "dane", "ile?", persona=jarvis)[0]["content"]
    assert "Kim jesteś" not in plain and jarvis.prompt in with_persona
    assert with_persona.index(jarvis.prompt) < with_persona.index(pl.DATA_HEADER)
    summary = summary_messages(config, "Artykuł.", "kto?", jarvis)[0]["content"]
    assert jarvis.prompt in summary and summary.index("Kim jesteś") < summary.index("Artykuł.")
    assert "Kim jesteś" not in summary_messages(config, "Artykuł.", "kto?")[0]["content"]


def test_female_forms_of_fixed_replies() -> None:
    assert pl.gendered(pl.GUESS_QUESTION, "female").startswith(
        "Nie jestem pewna, czy dobrze usłyszałam."
    )
    repeat = pl.gendered(pl.ASK_TO_REPEAT, "female")
    assert repeat == "Przepraszam, źle zrozumiałam. Powtórz, proszę."
    assert pl.gendered("Zrozumiałem. Tytułem wstępu", "female") == "Zrozumiałam. Tytułem wstępu"
    assert pl.gendered(pl.NOT_UNDERSTOOD, "male") == pl.NOT_UNDERSTOOD
    assert pl.gendered(pl.NOT_UNDERSTOOD, None) == pl.NOT_UNDERSTOOD


def test_current_pipeline_by_context(hass: HomeAssistant) -> None:
    from homeassistant.components.assist_pipeline.pipeline import KEY_ASSIST_PIPELINE

    asked = Context()
    pipeline = SimpleNamespace(id="01elza", name="Pokój Dziewczyn", tts_voice="pl_PL-elza-medium")
    other = SimpleNamespace(context=Context(), pipeline=SimpleNamespace(id="x"))
    run = SimpleNamespace(context=asked, pipeline=pipeline)
    runs = {"01x": {"r0": other}, "01elza": {"r1": run}}
    assert agent_module.current_pipeline(hass, asked) is None  # no assist_pipeline
    hass.data[KEY_ASSIST_PIPELINE] = SimpleNamespace(
        pipeline_runs=SimpleNamespace(_pipeline_runs=runs)
    )
    assert agent_module.current_pipeline(hass, asked) == (
        "01elza",
        "Pokój Dziewczyn",
        "pl_PL-elza-medium",
    )
    assert agent_module.current_pipeline(hass, Context()) is None


ROUTER_YAML = """
topics:
  inne: {description: wszystko inne}
personas:
  elza:
    pipelines: [Elza]
    gender: female
    prompt: Jesteś Elzą z bajki Kraina lodu. Mówisz jako dziewczyna.
"""


async def _ask(hass: HomeAssistant, text: str):
    return await conversation.async_converse(
        hass, text, None, Context(), language="pl", agent_id=AGENT_ID
    )


@pytest.fixture
def elza_pipeline(hass: HomeAssistant, setup: MockConfigEntry, monkeypatch) -> list:
    path = Path(hass.config.path("assist", "router.yaml"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ROUTER_YAML, encoding="utf-8")
    pipeline = [("01elza", "Pokój Dziewczyn Elza", None)]
    monkeypatch.setattr(agent_module, "current_pipeline", lambda hass, context: pipeline[0])
    return pipeline


async def test_fixed_reply_in_the_persona_gender(hass: HomeAssistant, elza_pipeline, monkeypatch):
    monkeypatch.setattr(agent_module, "enrollment_reply", lambda hass: ("Nie znalazłem.", False))
    result = await _ask(hass, "cokolwiek")
    assert result.response.speech["plain"]["speech"] == "Nie znalazłam."
    elza_pipeline[0] = ("01ok", "Salon OK Nabu", None)  # another pipeline - no persona
    result = await _ask(hass, "cokolwiek")
    assert result.response.speech["plain"]["speech"] == "Nie znalazłem."


async def test_fallback_agent_gets_the_persona(
    hass: HomeAssistant, setup: MockConfigEntry, elza_pipeline
) -> None:
    from homeassistant.helpers import intent

    from custom_components.assist_router.const import CONF_FALLBACK_AGENT

    got = []

    class Recorder(conversation.AbstractConversationAgent):
        @property
        def supported_languages(self) -> list[str]:
            return ["pl"]

        async def async_process(self, user_input):
            got.append(user_input)
            response = intent.IntentResponse(language="pl")
            response.async_set_speech("Zrobiłem to.")
            return conversation.ConversationResult(response=response)

    other = MockConfigEntry(domain="test_fallback")
    other.add_to_hass(hass)
    conversation.async_set_agent(hass, other, Recorder())
    hass.config_entries.async_update_entry(setup, options={CONF_FALLBACK_AGENT: other.entry_id})
    await hass.async_block_till_done()

    await _ask(hass, "zrób mi kanapkę z serem")

    assert got[-1].extra_system_prompt == pl.PERSONA.format(
        persona="Jesteś Elzą z bajki Kraina lodu. Mówisz jako dziewczyna."
    )


@pytest.mark.parametrize("file_name", ["router.example.yaml", "router.example.pl.yaml"])
def test_example_personas_are_valid(file_name: str) -> None:
    """The commented personas of the example files work once uncommented."""
    import yaml

    lines = (Path(__file__).parents[1] / file_name).read_text(encoding="utf-8").splitlines()
    start = lines.index("# personas:")
    block = []
    for line in lines[start:]:
        if not line.startswith("# ") or (block and not line.startswith("#  ")):
            break
        block.append(line[2:])
    config = parse_config({"topics": TOPICS, **yaml.safe_load("\n".join(block))})
    assert len(config.personas) >= 2 and all(p.prompt and p.gender for p in config.personas)
