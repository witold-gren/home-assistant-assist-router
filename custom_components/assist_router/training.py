"""Read-only export for the Assist Router trainer (home-assistant-assist-router-trainer).

The trainer runs on another machine and builds its training data from the files the router
uses: router.yaml, the log of unrecognized commands, the test files, the automations with a
`conversation` trigger (also those from packages) and custom_sentences. One command hands all of
it over, so the trainer needs only the Home Assistant address and an administrator's token.
Nothing is written and nothing is run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN, LOG_DIR, LOG_FILE, ROUTER_FILE
from .files import read_text
from .log_file import CsvLog
from .sentences import list_files, sentences_root

# the router's test files next to router.yaml (tools/model_benchmark.py)
TEST_FILES = ("model_test.yaml", "model_test_data.yaml")


def plain(value: Any) -> Any:
    """YAML values of an automation as JSON (dates and other objects as text)."""
    return json.loads(json.dumps(value, default=str))


def is_conversation_trigger(trigger: Any) -> bool:
    return (
        isinstance(trigger, dict)
        and (trigger.get("trigger") or trigger.get("platform")) == "conversation"
    )


def conversation_automations(hass: HomeAssistant) -> list[dict[str, Any]]:
    """The configuration of every automation with a `conversation` trigger, as written."""
    from homeassistant.components.automation import DATA_COMPONENT

    component = hass.data.get(DATA_COMPONENT)
    found = []
    for entity in component.entities if component else ():
        config = getattr(entity, "raw_config", None)
        if not isinstance(config, dict):
            continue
        triggers = config.get("triggers") or config.get("trigger") or []
        triggers = triggers if isinstance(triggers, list) else [triggers]
        if any(is_conversation_trigger(trigger) for trigger in triggers):
            found.append(plain(config))
    return found


def _read_files(directory: Path, names: tuple[str, ...]) -> dict[str, str]:
    return {name: read_text(directory / name) for name in names if (directory / name).is_file()}


@websocket_api.websocket_command({"type": f"{DOMAIN}/training/export"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_export(hass, connection, msg) -> None:
    """Everything the trainer reads, in one answer."""
    directory = Path(hass.config.path(LOG_DIR))
    integration = await async_get_integration(hass, DOMAIN)
    router_text = await hass.async_add_executor_job(read_text, directory / ROUTER_FILE)
    tests = await hass.async_add_executor_job(_read_files, directory, TEST_FILES)
    log = await CsvLog(hass, directory / LOG_FILE).async_rows()
    sentences = await hass.async_add_executor_job(list_files, sentences_root(hass))
    connection.send_result(
        msg["id"],
        {
            "version": str(integration.version),
            "language": hass.config.language,
            "router_yaml": router_text,
            "tests": tests,
            "log": log,
            "automations": conversation_automations(hass),
            "custom_sentences": [
                {"language": item["language"], "name": item["name"], "text": item["text"]}
                for item in sentences
            ],
        },
    )
