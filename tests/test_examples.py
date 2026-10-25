"""Example commands (action, sensor, options) and editing router.yaml in integration options."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
import yaml

from custom_components.assist_router import examples
from custom_components.assist_router.const import DOMAIN

from .conftest import OLLAMA, ROUTER_YAML
from .test_actions import (
    _called,
    dom as dom,  # home fixture with devices
)

SENSOR = "sensor.assist_router_przykladowe_komendy"

WRITTEN = {
    "szkoła": ["Jakie lekcje ma Kasia jutro?", "O której Jan kończy szkołę?", "Jaka jest pogoda?"],
    "sterowania": ["Zgaś światło w kuchni", "Włącz akwarium w salonie", "Wyłącz alarm w domu"],
}
PARSED = {
    "Zgaś światło w kuchni": {"intencja": "HassTurnOff", "domena": "light", "obszar": "Kuchnia"},
    "Włącz akwarium w salonie": {"intencja": "HassTurnOn", "nazwa": "akwarium", "obszar": "Salon"},
}


def _ollama(aioclient_mock: AiohttpClientMocker) -> None:
    """Model writing sentences, router (topic by keywords) and parsing of control commands."""

    async def handler(method, url, data):
        schema = json.dumps(data.get("format") or {})
        user = data["messages"][-1]["content"]
        if "zdania" in schema:
            topic = next((k for k in WRITTEN if k in user), None)
            content = {"zdania": WRITTEN.get(topic, [])}
        elif "intencja" in schema:
            content = {"intencja": None, "domena": None, "obszar": None, "pietro": None,
                       "nazwa": None, "wszystkie": False, "wartosc": None, "zmiana": None,
                       "element": None, "kolor": None, "barwa": None, "szukaj": None,
                       "rodzaj": None} | PARSED.get(user, {})  # fmt: skip
        elif re.search(r"lekcj|szkoł", user, re.IGNORECASE):
            content = {"temat": "lekcje"}
        elif re.search(r"światło|akwarium|alarm", user, re.IGNORECASE):
            content = {"temat": "sterowanie"}
        else:
            content = {"temat": "inne"}
        return AiohttpClientMockResponse(
            method, url, json={"message": {"content": json.dumps(content)}}
        )

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)


# --- functions without HA ---


def test_parse_sentences_dedupes_and_filters() -> None:
    content = json.dumps({"zdania": ["Włącz  światło", "włącz światło", "Tak", "- Zgaś lampę"]})
    assert examples.parse_sentences(content) == ["Włącz światło", "Zgaś lampę"]
    assert examples.parse_sentences("nie json") == []
    assert examples.parse_sentences(json.dumps({"zdania": "x"})) == []


def test_render_and_load_roundtrip(tmp_path: Path) -> None:
    result = {
        "lekcje": examples.TopicExamples(
            "szkoła", ["Jakie lekcje ma Kasia?"], [{"sentence": "Jaka pogoda?", "topic": "inne"}]
        )
    }
    path = tmp_path / examples.EXAMPLES_FILE
    path.write_text(examples.render(result, "gemma", "bielik"), encoding="utf-8")

    data = examples.load(path)

    assert data["lekcje"]["working"] == ["Jakie lekcje ma Kasia?"]
    assert data["lekcje"]["rejected"][0]["topic"] == "inne"
    assert path.read_text(encoding="utf-8").startswith("# Assist Router")
    assert examples.load(tmp_path / "brak.yaml") == {}


# --- action and sensor ---


async def test_generate_examples_checks_with_router_and_plan(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    """Only sentences the router sends to the topic and for which control gives a plan work;
    nothing is executed."""
    _ollama(aioclient_mock)

    response = await hass.services.async_call(
        DOMAIN, "generate_examples", {"per_topic": 5}, blocking=True, return_response=True
    )
    await hass.async_block_till_done()

    path = Path(hass.config.path("assist", examples.EXAMPLES_FILE))
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["lekcje"]["working"] == [
        "Jakie lekcje ma Kasia jutro?",
        "O której Jan kończy szkołę?",
    ]
    assert data["lekcje"]["rejected"] == [{"sentence": "Jaka jest pogoda?", "topic": "inne"}]
    assert data["sterowanie"]["working"] == ["Zgaś światło w kuchni", "Włącz akwarium w salonie"]
    assert data["sterowanie"]["rejected"][0]["sentence"] == "Wyłącz alarm w domu"
    assert "niezrozumiale" not in data  # gibberish topic skipped
    assert response["topics"]["lekcje"] == {"working": 2, "rejected": 1}
    assert not _called(dom)  # checked without executing

    state = hass.states.get(SENSOR)
    assert state.state == "4"
    assert state.attributes["topics"]["sterowanie"] == data["sterowanie"]["working"]
    assert state.attributes["rejected"]["lekcje"] == 1


async def test_generate_examples_only_chosen_topics(
    hass: HomeAssistant, dom: dict, aioclient_mock: AiohttpClientMocker
) -> None:
    _ollama(aioclient_mock)

    await hass.services.async_call(
        DOMAIN, "generate_examples", {"per_topic": 1, "topics": ["lekcje"]}, blocking=True
    )

    data = examples.load(Path(hass.config.path("assist", examples.EXAMPLES_FILE)))
    assert list(data) == ["lekcje"]
    assert data["lekcje"]["working"] == ["Jakie lekcje ma Kasia jutro?"]


async def test_sensor_without_examples(hass: HomeAssistant, router: MockConfigEntry) -> None:
    state = hass.states.get(SENSOR)
    assert state is not None and state.state == "unknown"


# --- options: router file ---


async def _menu(hass: HomeAssistant, entry: MockConfigEntry, step: str):
    menu = await hass.config_entries.options.async_init(entry.entry_id)
    assert menu["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": step}
    )


async def test_router_file_edit_saves_with_backup(
    hass: HomeAssistant, router: MockConfigEntry
) -> None:
    path = Path(hass.config.path("assist", "router.yaml"))
    form = await _menu(hass, router, "router_file")
    assert form["step_id"] == "router_file"
    assert form["data_schema"]({})["content"] == ROUTER_YAML  # current file content
    edited = ROUTER_YAML.replace("description: szkoła", "description: szkoła i lekcje")

    result = await hass.config_entries.options.async_configure(form["flow_id"], {"content": edited})

    assert result["type"] is FlowResultType.ABORT and result["reason"] == "router_saved"
    assert path.read_text(encoding="utf-8") == edited
    assert path.with_name("router.yaml.bak").read_text(encoding="utf-8") == ROUTER_YAML
    config = await router.runtime_data.router.async_get()
    assert config.topics["lekcje"].description == "szkoła i lekcje"


@pytest.mark.parametrize("content", ["topics: [", "people: {}\n", "topics:\n  x: {examples: 5}"])
async def test_router_file_invalid_is_not_saved(
    hass: HomeAssistant, router: MockConfigEntry, content: str
) -> None:
    path = Path(hass.config.path("assist", "router.yaml"))
    form = await _menu(hass, router, "router_file")

    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"content": content}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_router"}
    assert result["description_placeholders"]["error"]
    assert path.read_text(encoding="utf-8") == ROUTER_YAML


# --- options: example commands ---


async def test_examples_step_shows_preview_and_generates(
    hass: HomeAssistant, router: MockConfigEntry
) -> None:
    path = Path(hass.config.path("assist", examples.EXAMPLES_FILE))
    path.write_text(
        examples.render(
            {"lekcje": examples.TopicExamples("szkoła", ["Jakie lekcje ma Kasia?"])}, "g", "b"
        ),
        encoding="utf-8",
    )
    form = await _menu(hass, router, "examples")
    assert "- Jakie lekcje ma Kasia?" in form["description_placeholders"]["examples"]
    summary = {"file": str(path), "topics": {"lekcje": {"working": 3, "rejected": 1}}}

    release = asyncio.Event()

    async def slow(per_topic: int) -> dict:
        await release.wait()  # generation in progress - the dialog shows progress
        return summary

    with patch.object(
        router.runtime_data.agent, "async_generate_examples", AsyncMock(side_effect=slow)
    ) as generate:
        progress = await hass.config_entries.options.async_configure(
            form["flow_id"], {"generate": True, "per_topic": 3}
        )
        assert progress["type"] is FlowResultType.SHOW_PROGRESS, progress
        assert progress["progress_action"] == "generating"
        release.set()
        await hass.async_block_till_done()
        # once the task finishes, HA itself goes through the „progress done” step
        result = await hass.config_entries.options.async_configure(progress["flow_id"])

    generate.assert_awaited_once_with(3)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "examples_saved"
    assert result["description_placeholders"]["working"] == "3"


async def test_examples_step_without_generating_closes(
    hass: HomeAssistant, router: MockConfigEntry
) -> None:
    form = await _menu(hass, router, "examples")
    assert form["data_schema"]({})["generate"] is True  # no file - generate by default
    result = await hass.config_entries.options.async_configure(form["flow_id"], {"generate": False})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "examples_closed"


# --- unrecognized log: preview, sensor, clearing ---

LOG_SENSOR = "sensor.assist_router_nierozpoznane_komendy"


async def _log_rows(entry: MockConfigEntry, count: int) -> None:
    for i in range(count):
        await entry.runtime_data.log.async_append(
            {"timestamp": f"2026-10-23 10:0{i}", "area": "Kuchnia", "kind": "no_intent_match",
             "text": f"zdanie {i} | z kreską", "response": "Nie rozumiem.", "speaker": "Kasia"}
        )  # fmt: skip


async def test_log_step_shows_table_newest_first(
    hass: HomeAssistant, router: MockConfigEntry
) -> None:
    await _log_rows(router, 3)
    form = await _menu(hass, router, "log")

    table = form["description_placeholders"]["table"]
    assert form["description_placeholders"]["count"] == "3"
    assert table.splitlines()[0].startswith("| Kiedy | Pokój | Mówca | Usłyszane")
    assert table.index("zdanie 2") < table.index("zdanie 0")  # newest on top
    assert "zdanie 2 / z kreską" in table  # „|” does not break the table
    await hass.async_block_till_done()
    state = hass.states.get(LOG_SENSOR)
    assert state.state == "3"
    assert state.attributes["last"][0]["text"] == "zdanie 2 | z kreską"


async def test_log_step_clears_with_backup(hass: HomeAssistant, router: MockConfigEntry) -> None:
    await _log_rows(router, 2)
    path = router.runtime_data.log.path
    form = await _menu(hass, router, "log")

    result = await hass.config_entries.options.async_configure(form["flow_id"], {"clear": True})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT and result["reason"] == "log_cleared"
    assert result["description_placeholders"]["count"] == "2"
    assert await router.runtime_data.log.async_rows() == []
    assert "zdanie 1" in path.with_name(path.name + ".bak").read_text(encoding="utf-8")
    assert hass.states.get(LOG_SENSOR).state == "0"


async def test_clear_log_action(hass: HomeAssistant, router: MockConfigEntry) -> None:
    await _log_rows(router, 4)
    response = await hass.services.async_call(
        DOMAIN, "clear_log", {}, blocking=True, return_response=True
    )
    assert response["cleared"] == 4
    await _log_rows(router, 1)  # the log still works after clearing
    assert len(await router.runtime_data.log.async_rows()) == 1


def test_files_with_old_polish_keys_are_read(tmp_path: Path) -> None:
    """router_examples.yaml written before 0.1.0 used Polish keys."""
    old = {"lekcje": {"opis": "szkoła", "dzialaja": ["a", "b"], "odrzucone": [{"zdanie": "c"}]}}
    assert examples.working(old["lekcje"]) == ["a", "b"]
    assert examples.rejected(old["lekcje"]) == [{"zdanie": "c"}]
