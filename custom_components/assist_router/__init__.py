"""Assist Router: Assist with a question router and a log of unrecognized commands."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .const import DOMAIN, LOG_DIR, LOG_FILE, ROUTER_FILE, TITLE
from .languages import LANG, set_language
from .log_file import CsvLog
from .router import RouterConfigFile

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .conversation import AssistRouterAgent

PLATFORMS: list[Platform] = [Platform.CONVERSATION, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

GENERATE_SCHEMA = vol.Schema(
    {
        vol.Optional("per_topic", default=5): vol.All(vol.Coerce(int), vol.Range(1, 20)),
        vol.Optional("topics"): vol.All(cv.ensure_list, [cv.string]),
    }
)


@dataclass
class RuntimeData:
    log: CsvLog
    router: RouterConfigFile
    agent: AssistRouterAgent | None = None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def generate_examples(call: ServiceCall) -> ServiceResponse:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        agent: Any = entries[0].runtime_data.agent if entries else None
        if agent is None:
            raise HomeAssistantError("Assist Router is not set up")
        topics = set(call.data["topics"]) if call.data.get("topics") else None
        return await agent.async_generate_examples(call.data["per_topic"], topics)

    async def clear_log(call: ServiceCall) -> ServiceResponse:
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("Assist Router is not set up")
        log = entries[0].runtime_data.log
        return {"cleared": await log.async_clear(), "backup": str(log.path) + ".bak"}

    hass.services.async_register(
        DOMAIN,
        "clear_log",
        clear_log,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "generate_examples",
        generate_examples,
        schema=GENERATE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[RuntimeData]) -> bool:
    if entry.title != TITLE:
        # entries of early test versions had another title
        hass.config_entries.async_update_entry(entry, title=TITLE)
    # the language pack: the HA language when there is a pack for it (router.yaml can
    # choose another one with `language:`), otherwise the default pack
    if not set_language(hass.config.language):
        _LOGGER.debug("No language pack for %s, using %s", hass.config.language, LANG.code)
    entry.runtime_data = RuntimeData(
        log=CsvLog(hass, Path(hass.config.path(LOG_DIR, LOG_FILE))),
        router=RouterConfigFile(hass, Path(hass.config.path(LOG_DIR, ROUTER_FILE))),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # new options (e.g. another model) = reload, so the models are loaded right away
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry[RuntimeData]) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[RuntimeData]) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
