"""Read-only export for the Assist Router trainer (home-assistant-assist-router-trainer).

The trainer runs on another machine and builds its training data from the files the router
uses: router.yaml, the log of unrecognized commands, the test files, the automations with a
`conversation` trigger (also those from packages) and custom_sentences. One command hands all of
it over, so the trainer needs only the Home Assistant address and an administrator's token.
Two more commands hand over the home's own voice commands - the speech-to-text WAV files Home
Assistant keeps with ``assist_pipeline: debug_recording_dir`` - first the list, then the files
in parts. Nothing is written and nothing is run.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
import voluptuous as vol

from .const import DOMAIN, LOG_DIR, LOG_FILE, ROUTER_FILE
from .files import read_text
from .log_file import CsvLog
from .sentences import list_files, sentences_root

# the router's test files next to router.yaml (tools/model_benchmark.py)
TEST_FILES = ("model_test.yaml", "model_test_data.yaml")
# one answer with recordings carries at most this much audio (base64 adds a third)
RECORDINGS_PART = 4 * 1024 * 1024
MAX_PATHS = 500


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


# --- the home's voice commands (assist_pipeline: debug_recording_dir) ---------------------------


def recordings_dir(hass: HomeAssistant) -> Path | None:
    """The folder Home Assistant records the voice pipelines to, None when it is not set."""
    from homeassistant.components.assist_pipeline.const import (
        CONF_DEBUG_RECORDING_DIR,
        DATA_CONFIG,
    )

    folder = (hass.data.get(DATA_CONFIG) or {}).get(CONF_DEBUG_RECORDING_DIR)
    return Path(folder) if folder else None


def speech_files(root: Path) -> list[dict[str, Any]]:
    """The speech-to-text recordings (``<device>/<pipeline>/<run>/01_stt….wav``), oldest first."""
    if not root.is_dir():
        return []
    found = []
    for path in root.rglob("*.wav"):
        if "stt" not in path.name or not path.is_file():
            continue  # the wake word recordings are not what was said
        stat = path.stat()
        found.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
        )
    return sorted(found, key=lambda item: (item["modified"], item["path"]))


def read_recordings(root: Path, paths: list[str], limit: int | None = None) -> list[dict]:
    """The files asked for, base64, until ``limit`` bytes (at least one); anything outside the
    folder or not a WAV is left out."""
    limit = RECORDINGS_PART if limit is None else limit
    base = root.resolve()
    out, total = [], 0
    for relative in paths:
        path = (base / relative).resolve()
        if path.suffix != ".wav" or not path.is_relative_to(base) or not path.is_file():
            continue
        size = path.stat().st_size
        if out and total + size > limit:
            break
        out.append({"path": relative, "data": base64.b64encode(path.read_bytes()).decode()})
        total += size
    return out


@websocket_api.websocket_command({"type": f"{DOMAIN}/training/recordings"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_recordings(hass, connection, msg) -> None:
    """The list of the home's voice command recordings (no audio)."""
    root = recordings_dir(hass)
    files = await hass.async_add_executor_job(speech_files, root) if root else []
    connection.send_result(msg["id"], {"configured": root is not None, "files": files})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/training/recording_files",
        vol.Required("paths"): vol.All([str], vol.Length(max=MAX_PATHS)),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_recording_files(hass, connection, msg) -> None:
    """Recordings by their paths from the list; the rest of ``paths`` in the next call."""
    root = recordings_dir(hass)
    files = await hass.async_add_executor_job(read_recordings, root, msg["paths"]) if root else []
    connection.send_result(msg["id"], {"files": files})
