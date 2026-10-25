"""Fallback agent (e.g. Bielik): answers unrecognized commands."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Literal
import uuid

from homeassistant.components import conversation
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.assist_router.const import (
    CONF_FALLBACK_AGENT,
    CONF_FALLBACK_TIMEOUT,
    CONF_LOG_UNRECOGNIZED,
)

from .conftest import AGENT_ID


class FakeLLM(conversation.AbstractConversationAgent):
    """Test fallback agent: replies with fixed text, an error or a delay."""

    def __init__(
        self,
        answer: str = "Kanapkę zrobisz sam, ja nie mam rąk.",
        delay: float = 0,
        error: bool = False,
    ) -> None:
        self.answer, self.delay, self.error = answer, delay, error
        self.calls: list[str] = []
        self.conversation_ids: list[str | None] = []

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return "*"

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        self.calls.append(user_input.text)
        self.conversation_ids.append(user_input.conversation_id)
        if self.delay:
            await asyncio.sleep(self.delay)
        response = intent.IntentResponse(language=user_input.language)
        if self.error:
            response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, "model niedostępny")
        else:
            response.async_set_speech(self.answer)
        return conversation.ConversationResult(
            response=response, conversation_id=user_input.conversation_id or uuid.uuid4().hex
        )


async def _with_fallback(
    hass: HomeAssistant, setup: MockConfigEntry, llm: FakeLLM, timeout: int = 30
) -> None:
    llm_entry = MockConfigEntry(domain="test_llm")
    llm_entry.add_to_hass(hass)
    conversation.async_set_agent(hass, llm_entry, llm)
    hass.config_entries.async_update_entry(
        setup, options={CONF_FALLBACK_AGENT: llm_entry.entry_id, CONF_FALLBACK_TIMEOUT: timeout}
    )


async def _ask(hass: HomeAssistant, text: str, conversation_id: str | None = None):
    return await conversation.async_converse(
        hass, text, conversation_id, Context(), language="pl", agent_id=AGENT_ID
    )


def _rows(hass: HomeAssistant) -> list[dict[str, str]]:
    path = Path(hass.config.path("assist", "unrecognized_commands.csv"))
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


async def test_unrecognized_goes_to_fallback(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    llm = FakeLLM()
    await _with_fallback(hass, setup, llm)

    result = await _ask(hass, "zrób mi kanapkę")

    assert llm.calls == ["zrób mi kanapkę"]
    assert result.response.speech["plain"]["speech"] == "Kanapkę zrobisz sam, ja nie mam rąk."
    rows = _rows(hass)
    assert len(rows) == 1 and rows[0]["kind"] == "no_intent_match"
    assert rows[0]["response"] == "Kanapkę zrobisz sam, ja nie mam rąk."


async def test_recognized_command_skips_fallback(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    llm = FakeLLM()
    await _with_fallback(hass, setup, llm)

    result = await _ask(hass, "która godzina")

    assert llm.calls == []
    assert result.response.response_type != intent.IntentResponseType.ERROR


async def test_unknown_device_skips_fallback(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    llm = FakeLLM()
    await _with_fallback(hass, setup, llm)
    hass.states.async_set("light.kuchnia", "off", {"friendly_name": "Kuchnia"})
    async_expose_entity(hass, conversation.DOMAIN, "light.kuchnia", True)

    result = await _ask(hass, "włącz lampę przy biurku")

    assert llm.calls == []
    assert result.response.error_code == intent.IntentResponseErrorCode.NO_VALID_TARGETS


async def test_fallback_error_keeps_repeat_message(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    await _with_fallback(hass, setup, FakeLLM(error=True))

    result = await _ask(hass, "zrób mi kanapkę")

    assert (
        result.response.speech["plain"]["speech"]
        == "Powiedziałeś: zrób mi kanapkę. Niestety nie mogę tego zrozumieć."
    )
    assert _rows(hass)[0]["response"].startswith("Powiedziałeś")


async def test_fallback_timeout_keeps_repeat_message(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    await _with_fallback(hass, setup, FakeLLM(delay=2), timeout=1)

    result = await _ask(hass, "zrób mi kanapkę")

    assert result.response.speech["plain"]["speech"].startswith("Powiedziałeś: zrób mi kanapkę")


async def test_missing_fallback_agent_keeps_repeat_message(
    hass: HomeAssistant, setup: MockConfigEntry
) -> None:
    hass.config_entries.async_update_entry(
        setup, options={CONF_FALLBACK_AGENT: "conversation.nie_ma_takiego"}
    )

    result = await _ask(hass, "zrób mi kanapkę")

    assert result.response.speech["plain"]["speech"].startswith("Powiedziałeś: zrób mi kanapkę")


async def test_options_flow(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    menu = await hass.config_entries.options.async_init(setup.entry_id)
    assert menu["type"] == "menu"
    flow = await hass.config_entries.options.async_configure(
        menu["flow_id"], {"next_step_id": "settings"}
    )
    assert flow["type"] == "form" and flow["step_id"] == "settings"
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {CONF_FALLBACK_AGENT: "conversation.bielik", CONF_FALLBACK_TIMEOUT: 20}
    )
    assert result["type"] == "create_entry"
    assert setup.options == {
        CONF_FALLBACK_AGENT: "conversation.bielik",
        CONF_FALLBACK_TIMEOUT: 20,
        CONF_LOG_UNRECOGNIZED: True,
    }


async def test_fallback_gets_own_conversation(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    """The fallback agent doesn't see HA's error from history; the next question has its context."""
    llm = FakeLLM()
    await _with_fallback(hass, setup, llm)

    first = await _ask(hass, "opowiedz jakiś kawał")
    second = await _ask(hass, "opowiedz jeszcze jeden", first.conversation_id)

    # first question: a new agent conversation, not the HA one with the error message
    assert llm.conversation_ids[0] is None
    # second: the same agent conversation as before, different from the HA one
    assert llm.conversation_ids[1] is not None
    assert llm.conversation_ids[1] != first.conversation_id
    # the device still continues the HA conversation
    assert second.conversation_id == first.conversation_id


async def test_fallback_speech_is_stripped(hass: HomeAssistant, setup: MockConfigEntry) -> None:
    await _with_fallback(hass, setup, FakeLLM(answer="\nKawał o Krakowie.  "))

    result = await _ask(hass, "opowiedz jakiś kawał")

    assert result.response.speech["plain"]["speech"] == "Kawał o Krakowie."
    assert _rows(hass)[0]["response"] == "Kawał o Krakowie."
