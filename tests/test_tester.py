"""The editor's tester: the way of a sentence on a router.yaml not saved yet. Home Assistant only
recognizes, control is only planned, a topic's command is never sent, the fallback agent is not
asked and nothing goes to the log; the models answer as they would."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

from custom_components.assist_router.const import CONF_ANSWER_MODEL, DOMAIN

from .conftest import OLLAMA, ROUTER_YAML
from .test_control import CONTROL_TOPIC, _home
from .test_router import _answer, _rows

DRAFT = ROUTER_YAML.replace("  inne:\n", CONTROL_TOPIC + "  inne:\n")


def chat(aioclient_mock: AiohttpClientMocker, topics: dict[str, str], parsed: dict | None = None):
    """Ollama: the router's topic by a word of the question, the answer model's text, and the
    parsing of a control command."""

    async def handler(method, url, data):
        if "intencja" in json.dumps(data.get("format", {})):
            content = {"intencja": None, "domena": None, "obszar": None, "pietro": None,
                       "nazwa": None, "wszystkie": False, "wartosc": None, "zmiana": None,
                       "element": None, "kolor": None, "barwa": None, "szukaj": None,
                       "rodzaj": None, "wykonawca": None, "radio": False}  # fmt: skip
            content |= parsed or {}
            return AiohttpClientMockResponse(
                method, url, json={"message": {"content": json.dumps(content)}}
            )
        if data["model"] == "gemma-mala":
            return AiohttpClientMockResponse(
                method, url, json={"message": {"content": "Paliwa starczy na 300 km."}}
            )
        question = data["messages"][-1]["content"]
        topic = next((t for word, t in topics.items() if word in question), "inne")
        return AiohttpClientMockResponse(method, url, json=_answer(topic))

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)


async def trace(client, sentence: str, text: str = DRAFT, **options) -> dict:
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/editor/test", "text": text, "sentence": sentence, **options}
    )
    answer = await client.receive_json()
    assert answer["success"], answer
    return answer["result"]


async def answer_model(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ANSWER_MODEL: "gemma-mala"}
    )
    await hass.async_block_till_done()


async def test_a_question_goes_to_its_topic_and_its_data_and_answer(
    hass, router, aioclient_mock, hass_ws_client
) -> None:
    await answer_model(hass, router)
    hass.states.async_set("sensor.auto_zasieg", "300", {"friendly_name": "Auto zasięg"})
    chat(aioclient_mock, {"paliw": "auto"})
    client = await hass_ws_client(hass)
    result = await trace(client, "ile mam paliwa")
    assert result["ha"]["match"] is None
    assert result["router"]["topic"] == "auto" and result["router"]["model"] == "bielik-1.5b"
    assert result["data"]["lines"] == ["Auto zasięg: 300"]
    assert result["outcome"] == "answer"
    assert result["speech"] == "Paliwa starczy na 300 km."
    assert result["answer"]["messages"][1]["content"] == "ile mam paliwa"
    assert _rows(hass) == []  # the tester writes nothing to the log


async def test_the_draft_is_used_and_compared_with_the_saved_file(
    hass, router, aioclient_mock, hass_ws_client
) -> None:
    chat(aioclient_mock, {"paliw": "paliwo"})
    draft = DRAFT.replace("  auto:\n", "  paliwo:\n    description: paliwo\n  auto:\n")
    client = await hass_ws_client(hass)
    result = await trace(client, "ile mam paliwa", text=draft, compare=True)
    assert result["router"]["topic"] == "paliwo"
    # the saved file has no such topic, so its router answers otherwise
    assert result["saved_topic"] is None


async def test_control_is_only_planned(hass, router, aioclient_mock, hass_ws_client) -> None:
    await _home(hass)
    calls = async_mock_service(hass, "light", "turn_off")
    chat(
        aioclient_mock,
        {"zgaś": "sterowanie"},
        {"intencja": "HassTurnOff", "domena": "light", "obszar": "Kuchnia"},
    )
    client = await hass_ws_client(hass)
    result = await trace(client, "zgaś światło w kuchni ze skrzydłem")
    assert result["router"]["topic"] == "sterowanie"
    assert result["control"]["plan"]["intent"] == "HassTurnOff"
    assert result["outcome"] == "control_execute"
    await hass.async_block_till_done()
    assert calls == []
    assert hass.states.get("light.kuchnia_sufit").state == "on"


async def test_a_lock_is_planned_with_its_question(
    hass, router, aioclient_mock, hass_ws_client
) -> None:
    await _home(hass)
    calls = async_mock_service(hass, "lock", "unlock")
    chat(
        aioclient_mock,
        {"zamek": "sterowanie"},
        {"intencja": "HassTurnOff", "domena": "lock", "nazwa": "drzwi wejściowe"},
    )
    client = await hass_ws_client(hass)
    result = await trace(client, "otwórz zamek drzwi")
    assert result["outcome"] == "control_confirm"
    assert "Drzwi wejściowe" in result["speech"]
    assert calls == []


async def test_a_command_sentence_is_recognized_but_never_sent(
    hass, router, aioclient_mock, hass_ws_client
) -> None:
    chat(aioclient_mock, {"plany": "kalendarz"})
    fired = []
    hass.bus.async_listen("automation_triggered", fired.append)
    client = await hass_ws_client(hass)
    result = await trace(client, "jakie mam plany jutro")
    command = result["data"]["command"]
    assert command["sentence"] == "jakie są jutro wydarzenia"
    assert command["ha"]["match"] is True and command["ha"]["source"] == "trigger"
    await hass.async_block_till_done()
    assert fired == []


async def test_a_sentence_home_assistant_knows_stops_there(
    hass, router, aioclient_mock, hass_ws_client
) -> None:
    await _home(hass)
    chat(aioclient_mock, {})
    calls = async_mock_service(hass, "light", "turn_on")
    client = await hass_ws_client(hass)
    result = await trace(client, "włącz Lampa stojąca")
    assert result["outcome"] == "ha"
    assert result["ha"]["intent"] == "HassTurnOn"
    assert "router" not in result
    assert calls == []
    # straight to the router when asked
    skipped = await trace(client, "włącz Lampa stojąca", skip_ha=True)
    assert "ha" not in skipped and skipped["router"]["topic"] == "inne"


async def test_no_topic_goes_to_the_fallback_without_asking_it(
    hass, router, aioclient_mock, hass_ws_client
) -> None:
    async def broken(method, url, data):
        return AiohttpClientMockResponse(method, url, status=500)

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=broken)
    client = await hass_ws_client(hass)
    result = await trace(client, "zaśpiewaj coś")
    assert result["router"]["topic"] is None
    assert result["outcome"] == "fallback"


async def test_without_the_agent_or_with_a_bad_text(hass, router, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/editor/test", "text": "topics: [a", "sentence": "x"}
    )
    assert (await client.receive_json())["error"]["code"] == "invalid"
    await hass.config_entries.async_unload(router.entry_id)
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/editor/test", "text": DRAFT, "sentence": "x"}
    )
    answer = await client.receive_json()
    assert not answer["success"]


async def test_only_administrators_test(hass, router, hass_ws_client, hass_admin_user) -> None:
    hass_admin_user.groups = []
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/editor/test", "text": DRAFT, "sentence": "x"}
    )
    assert (await client.receive_json())["error"]["code"] == "unauthorized"


def test_the_file_is_not_touched(hass: HomeAssistant) -> None:
    """The tester has no command that writes: only the editor's save does."""
    source = Path(__file__).parents[1] / "custom_components" / DOMAIN / "tester.py"
    text = source.read_text(encoding="utf-8")
    for call in (
        ".write_text(",
        "._write_log(",
        "._execute(",
        "._ask_fallback(",
        "._ask_home_assistant(",
    ):
        assert call not in text, call
