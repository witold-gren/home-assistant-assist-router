"""„Kto to mówi?” - answer from the voice recognition result (Assist Speaker ID)."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.assist_router import voice

from .test_router import _ask, _rows, _speech

NAMES = {"kasia": "Kasia", "tosia": "Tosia", "tomek": "Tomek"}


def _result(speaker=None, score=0.0, scores=None, reason="match"):
    return SimpleNamespace(speaker=speaker, score=score, scores=scores or {}, reason=reason)


@pytest.mark.parametrize(
    "text",
    [
        "Kto to mówi?",
        "Kim jestem?",
        "Jak mnie rozpoznajesz?",
        "Kto do ciebie mówi?",
        "Jak rozpoznajesz ten głos?",
        "Co to za głos?",
        "Czyj to głos?",
        "Czy wiesz, kim jestem?",
        "Powiedz mi, kto teraz do ciebie mówi.",
        "Rozpoznajesz mnie?",
    ],
)
def test_who_speaks_questions(text: str) -> None:
    assert voice.is_who_speaks(text)


@pytest.mark.parametrize(
    "text", ["Kto jest w domu?", "Jaki jest plan lekcji?", "Kim był Kopernik?"]
)
def test_other_questions_are_not_who_speaks(text: str) -> None:
    assert not voice.is_who_speaks(text)


def test_answer_recognised_with_runner_up() -> None:
    result = _result("kasia", 0.823, {"kasia": 0.823, "tosia": 0.351, "tomek": 0.1})
    assert voice.answer(result, NAMES) == (
        "Mówi Kasia, podobieństwo 82 procent. Następna osoba: Tosia, 35 procent."
    )


def test_answer_unknown_and_unsure() -> None:
    unknown = _result(None, 0.41, {"tomek": 0.41, "kasia": 0.2}, "tomek below threshold 0.50")
    unsure = _result(None, 0.62, {"kasia": 0.62, "tosia": 0.6}, "kasia too close to tosia")
    assert voice.answer(unknown, NAMES) == (
        "Nie rozpoznaję tego głosu. Najbliżej: Tomek, 41 procent, a do rozpoznania "
        "potrzeba 50 procent. Następna osoba: Kasia, 20 procent."
    )
    assert voice.answer(unsure, NAMES) == (
        "Nie jestem pewien. Najbardziej podobne głosy: Kasia 62 procent i Tosia 60 procent."
    )


def test_answer_unknown_without_threshold_in_reason() -> None:
    result = _result(None, 0.53, {"tomek": 0.53}, "no match")
    assert voice.answer(result, NAMES) == "Nie rozpoznaję tego głosu. Najbliżej: Tomek, 53 procent."


def test_answer_short_no_prints_no_voice() -> None:
    assert voice.answer(_result(reason="too short (0.6 s of speech)"), NAMES) == voice.TOO_SHORT
    assert voice.answer(_result(reason="no enrolled speakers"), NAMES) == voice.NO_PRINTS
    assert voice.answer(None, NAMES) == voice.NO_VOICE
    assert voice.answer(_result("jan", 0.7, {"jan": 0.7}), {}) == (
        "Mówi Jan, podobieństwo 70 procent."
    )


async def test_agent_answers_who_speaks_without_models(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.assist_router import conversation as agent_module

    monkeypatch.setattr(
        agent_module,
        "speaker_result",
        lambda hass: _result("kasia", 0.8, {"kasia": 0.8, "jan": 0.3}),
    )
    aioclient_mock.mock_calls.clear()

    result = await _ask(hass, "Kto to mówi?")

    # names from router.yaml (people), next in the queue
    assert (
        _speech(result) == "Mówi Kasia, podobieństwo 80 procent. Następna osoba: Jan, 30 procent."
    )
    assert not aioclient_mock.mock_calls
    assert _rows(hass) == []


# --- announcement (intercom) ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Ogłoszenie, dzieci proszę przyjść na obiad.", True),
        ("Komunikat: wychodzimy za pięć minut", True),
        ("Do wszystkich: kolacja gotowa", True),
        ("Intercom, Ola zejdź na dół", True),
        ("Jakie są nowe ogłoszenia w Librusie?", False),  # word not at the start
        ("Ogłoszenia z Librusa", False),  # another form - a question about Librus
        ("Wszystkich świętych jest w sobotę", False),
    ],
)
def test_is_announcement(text: str, expected: bool) -> None:
    assert voice.is_announcement(text) is expected


async def test_announcement_plays_recording_without_models(
    hass: HomeAssistant,
    router: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.assist_router import conversation as agent_module

    calls = []

    async def fake_announce(hass, exclude, media_players):
        calls.append((exclude, media_players))
        return ["assist_satellite.salon"]

    monkeypatch.setattr(agent_module, "announce_last", fake_announce)
    aioclient_mock.mock_calls.clear()

    result = await _ask(hass, "Ogłoszenie, dzieci proszę przyjść na obiad")

    assert _speech(result) == voice.ANNOUNCED
    assert calls == [(None, [])]  # typed in the test - no source satellite
    assert not aioclient_mock.mock_calls


async def test_announcement_without_recording_goes_on(
    hass: HomeAssistant, router: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    from custom_components.assist_router import conversation as agent_module

    async def no_recording(hass, exclude, media_players):
        return None

    monkeypatch.setattr(agent_module, "announce_last", no_recording)

    result = await _ask(hass, "Ogłoszenie, dzieci proszę przyjść na obiad")

    assert _speech(result) != voice.ANNOUNCED  # still the normal path (HA reads the text)


async def test_announce_last_prefers_players_when_supported(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Speaker ID 0.1.1+ gets prefer_players=True (HomePod instead of the satellite in the
    same room); 0.1.0 without this option - called as before."""
    import sys
    import types

    from custom_components.assist_router.conversation import announce_last

    calls = []

    async def new_api(hass, *, exclude=None, media_players=None, prefer_players=False):
        calls.append(prefer_players)
        return ["media_player.homepod"]

    async def old_api(hass, *, exclude=None, media_players=None):
        calls.append("old")
        return ["assist_satellite.salon"]

    for api in (new_api, old_api):
        module = types.ModuleType("custom_components.speaker_id.api")
        module.async_announce_last = api
        monkeypatch.setitem(sys.modules, "custom_components.speaker_id.api", module)
        await announce_last(hass, "assist_satellite.kuchnia", ["media_player.homepod"])
    assert calls == [True, "old"]


async def test_announce_players_from_router_yaml(hass: HomeAssistant) -> None:
    from custom_components.assist_router.router import parse_config

    config = parse_config(
        {"topics": {"inne": {"description": "x"}}, "announce_players": ["media_player.homepod"]}
    )
    assert config.announce_players == ("media_player.homepod",)
