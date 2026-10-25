"""Agent: recognized commands unchanged, unrecognized ones repeated and logged."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

from homeassistant.components import conversation
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, intent
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.assist_router.const import COLUMNS, EVENT_UNRECOGNIZED

from .conftest import AGENT_ID


async def _ask(hass: HomeAssistant, text: str, device_id: str | None = None):
    return await conversation.async_converse(
        hass, text, None, Context(), language="pl", agent_id=AGENT_ID, device_id=device_id
    )


def _rows(hass: HomeAssistant) -> list[dict[str, str]]:
    path = Path(hass.config.path("assist", "unrecognized_commands.csv"))
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


async def test_recognized_command_is_untouched(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    result = await _ask(hass, "która godzina")
    assert result.response.response_type != intent.IntentResponseType.ERROR
    assert "Powiedziałeś" not in result.response.speech["plain"]["speech"]
    assert _rows(hass) == []


async def test_unrecognized_is_repeated_and_logged(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    events = async_capture_events(hass, EVENT_UNRECOGNIZED)
    area = ar.async_get(hass).async_create("Kuchnia")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=setup.entry_id, identifiers={("test", "sat")}, name="Kuchnia Voice"
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)

    result = await _ask(hass, "zrób mi  kanapkę", device_id=device.id)

    speech = result.response.speech["plain"]["speech"]
    assert speech == "Powiedziałeś: zrób mi kanapkę. Niestety nie mogę tego zrozumieć."
    assert result.response.error_code == intent.IntentResponseErrorCode.NO_INTENT_MATCH
    rows = _rows(hass)
    assert len(rows) == 1
    assert list(rows[0]) == list(COLUMNS)
    assert rows[0]["kind"] == "no_intent_match"
    assert rows[0]["text"] == "zrób mi kanapkę"
    assert rows[0]["area"] == "Kuchnia"
    assert rows[0]["device"] == "Kuchnia Voice"
    assert rows[0]["response"] == speech
    assert len(events) == 1 and events[0].data["text"] == "zrób mi kanapkę"


async def test_unknown_device_keeps_ha_message_and_is_logged(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    hass.states.async_set("light.kuchnia", "off", {"friendly_name": "Kuchnia"})
    async_expose_entity(hass, conversation.DOMAIN, "light.kuchnia", True)

    result = await _ask(hass, "włącz lampę przy biurku")

    assert result.response.error_code == intent.IntentResponseErrorCode.NO_VALID_TARGETS
    speech = result.response.speech["plain"]["speech"]
    assert "Powiedziałeś" not in speech
    rows = _rows(hass)
    assert len(rows) == 1
    assert rows[0]["kind"] == "no_valid_targets"
    assert rows[0]["text"] == "włącz lampę przy biurku"
    assert rows[0]["response"] == speech


async def test_empty_text(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    result = await _ask(hass, "   ")
    if result.response.error_code == intent.IntentResponseErrorCode.NO_INTENT_MATCH:
        assert result.response.speech["plain"]["speech"] == "Nic nie usłyszałem."


async def test_log_failure_does_not_break_answer(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    with patch(
        "custom_components.assist_router.log_file.CsvLog._append", side_effect=OSError("dysk")
    ):
        result = await _ask(hass, "zrób mi kanapkę")
    assert result.response.speech["plain"]["speech"].startswith("Powiedziałeś: zrób mi kanapkę")


async def test_single_instance(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    result = await hass.config_entries.flow.async_init("assist_router", context={"source": "user"})
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"
