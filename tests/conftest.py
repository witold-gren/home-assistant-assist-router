"""Shared fixtures: HA in Polish with the built-in agent and our integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.assist_router.const import (
    CONF_OLLAMA_URL,
    CONF_ROUTER_KEEP_ALIVE,
    CONF_ROUTER_MODEL,
    CONF_ROUTER_TIMEOUT,
    DOMAIN,
)

AGENT_ID = "conversation.assist_router"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom_components in tests."""


@pytest.fixture
async def setup(hass: HomeAssistant, tmp_path) -> MockConfigEntry:
    # Each test gets its own config directory - otherwise the CSV file leaks between tests.
    hass.config.config_dir = str(tmp_path)
    hass.config.language = "pl"
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "conversation", {})
    assert await async_setup_component(hass, "intent", {})
    entry = MockConfigEntry(domain=DOMAIN, title="Assist z zapisem")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


OLLAMA = "http://ollama.test:11434"
WIKI = "https://pl.wikipedia.org/w/api.php"

ROUTER_YAML = """
household: "Domownicy: Tomek, Ania, dzieci: Kasia, Jan."
people:
  kasia: {name: Kasia, match: "kasi|katarz"}
  jan: Jan
topics:
  kalendarz:
    description: plany i wydarzenia
    examples: ["Co mam jutro w pracy?"]
    command: >-
      jakie są {{ 'jutro' if kiedy == 'jutro' else 'dzisiaj' }} wydarzenia
  lekcje:
    description: szkoła
    command: "o której {{ osoba }} kończy lekcje"
  auto:
    description: samochód
    entities: ["sensor.auto_*", "binary_sensor.auto_*"]
  wiedza:
    description: wiedza ogólna
    search: wikipedia
  inne:
    description: wszystko inne
"""


@pytest.fixture
async def router(
    hass: HomeAssistant, setup: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    """Router enabled: router.yaml + Ollama in options + automations with sentences."""
    # changing options reloads the integration, which loads the models into memory
    aioclient_mock.post(f"{OLLAMA}/api/generate", json={"done": True})
    path = Path(hass.config.path("assist", "router.yaml"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ROUTER_YAML, encoding="utf-8")
    hass.config_entries.async_update_entry(
        setup,
        options={
            CONF_OLLAMA_URL: OLLAMA,
            CONF_ROUTER_MODEL: "bielik-1.5b",
            CONF_ROUTER_TIMEOUT: 5,
            CONF_ROUTER_KEEP_ALIVE: -1,
        },
    )
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "triggers": {
                        "trigger": "conversation",
                        "command": ["jakie są (dzisiaj|jutro) wydarzenia"],
                    },
                    "actions": {"set_conversation_response": "Jutro o 17:30 robotyka."},
                },
                {
                    "triggers": {
                        "trigger": "conversation",
                        "command": ["o której {dziecko} kończy lekcje"],
                    },
                    "actions": {
                        "set_conversation_response": "{{ trigger.slots.dziecko }} kończy o 12:35."
                    },
                },
            ]
        },
    )
    await hass.async_block_till_done()
    aioclient_mock.mock_calls.clear()  # tests count only their own requests
    return setup
