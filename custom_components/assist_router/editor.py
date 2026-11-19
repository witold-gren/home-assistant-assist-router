"""The editor of the router on a computer: a panel for administrators that edits router.yaml as
text, so the comments of the file stay, with a draft kept on the server, checked before it is
saved, and a history to go back to.

The draft changes nothing: the router keeps reading router.yaml until the draft is saved. Saving
checks the text the way the router reads it, refuses to overwrite a file changed elsewhere
meanwhile (unless asked to), keeps the previous file as .bak and in the history, and the router
reads the new one at once, without a restart.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from http import HTTPStatus
from pathlib import Path
from typing import Any
import uuid

from aiohttp import web
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.frontend import async_remove_panel
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration
import voluptuous as vol
import yaml

from .const import DOMAIN, LOG_DIR, LOG_FILE, ROUTER_FILE
from .files import read_text, write_with_backup
from .languages import available_languages
from .learn import (
    TESTS_FILE,
    async_classify_sentences,
    async_run_tests,
    clean_test,
    dump_tests,
    read_tests,
    unrecognized_groups,
)
from .log_file import CsvLog
from .preview import async_sources_preview, config_checks, read_only_services
from .router import RouterConfig, parse_config
from .sentences import (
    check_sentences,
    file_path,
    known_intents,
    list_files,
    remove_file,
    sentences_root,
    text_hash as sentences_hash,
    write_file,
)
from .training import (
    websocket_export as websocket_training_export,
    websocket_recording_files as websocket_training_recording_files,
    websocket_recordings as websocket_training_recordings,
)

STATIC_URL = "/assist_router_static"
WWW_DIR = Path(__file__).parent / "www"
SERVED_SUFFIXES = {".js"}
STORAGE_KEY = f"{DOMAIN}.editor"
STORAGE_VERSION = 1
HISTORY_LIMIT = 30
PANEL_URL = "assist-router-editor"
PANEL_ELEMENT = "assist-router-editor"
PANEL_TITLES = {"pl": "Edytor Assist Routera"}
PANEL_TITLE = "Assist Router editor"
PANEL_ICON = "mdi:robot-outline"
DATA_EDITOR = f"{DOMAIN}_editor"

ERROR_INVALID = "invalid"
ERROR_NO_DRAFT = "no_draft"
ERROR_CONFLICT = "conflict"
ERROR_NOT_FOUND = "not_found"
ERROR_NO_AGENT = "no_agent"


def text_hash(text: str) -> str:
    """A short fingerprint of the file's text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def check_text(text: str) -> dict[str, Any]:
    """Whether the router can read this text as it reads router.yaml; its topics when it can."""
    try:
        config = parse_config(yaml.safe_load(text))
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as err:
        return {"ok": False, "error": str(err), "topics": []}
    return {"ok": True, "error": None, "topics": list(config.topics)}


def resolve_static_file(root: Path, relative_path: str) -> Path | None:
    """The file to serve, or None when the path leaves the folder or is not a module."""
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root.resolve()):
        return None
    if candidate.suffix not in SERVED_SUFFIXES or not candidate.is_file():
        return None
    return candidate


class AssistRouterStaticView(HomeAssistantView):
    """The editor's modules; public, as HA loads a panel's module before signing in."""

    url = f"{STATIC_URL}/{{path:.+}}"
    name = f"api:{DOMAIN}:static"
    requires_auth = False

    async def get(self, request: web.Request, path: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app["hass"]
        file_path = await hass.async_add_executor_job(resolve_static_file, WWW_DIR, path)
        if file_path is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        return web.FileResponse(file_path, headers={"Cache-Control": "no-cache"})


class EditorStore:
    """The draft and the history of router.yaml, in .storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict[str, Any] = {"draft": None, "history": [], "hidden": []}

    async def async_load(self) -> None:
        self.data = await self._store.async_load() or {"draft": None, "history": []}
        # sentences of the log hidden in the editor (added in a later version of the store)
        self.data.setdefault("hidden", [])

    async def async_save(self) -> None:
        await self._store.async_save(self.data)


def router_path(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(LOG_DIR, ROUTER_FILE))


async def async_setup_editor(hass: HomeAssistant, in_sidebar: bool = True) -> None:
    """The store, the commands and the static view once per start; the panel for administrators,
    in the sidebar or (without a title) only at its address."""
    if DATA_EDITOR not in hass.data:
        store = EditorStore(hass)
        await store.async_load()
        hass.data[DATA_EDITOR] = store
        for command in COMMANDS:
            websocket_api.async_register_command(hass, command)
        if hass.http is not None:
            hass.http.register_view(AssistRouterStaticView)
    if "frontend" not in hass.config.components:
        return
    integration = await async_get_integration(hass, DOMAIN)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=PANEL_TITLES.get(hass.config.language, PANEL_TITLE) if in_sidebar else None,
        sidebar_icon=PANEL_ICON if in_sidebar else None,
        module_url=f"{STATIC_URL}/editor/editor.js?v={integration.version}",
        require_admin=True,
    )


@callback
def async_unload_editor(hass: HomeAssistant) -> None:
    async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)


def _store(hass: HomeAssistant) -> EditorStore:
    return hass.data[DATA_EDITOR]


def _user(connection: websocket_api.ActiveConnection) -> str | None:
    return connection.user.id if connection.user else None


async def _file_text(hass: HomeAssistant) -> str:
    return await hass.async_add_executor_job(read_text, router_path(hass))


def tests_path(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(LOG_DIR, TESTS_FILE))


def _config_or_error(connection, msg, text: str) -> RouterConfig | None:
    """The router's configuration of a text; None after sending the error when it cannot read it."""
    try:
        return parse_config(yaml.safe_load(text))
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as err:
        connection.send_error(msg["id"], ERROR_INVALID, str(err))
        return None


async def _saved_config(hass: HomeAssistant) -> RouterConfig | None:
    try:
        return parse_config(yaml.safe_load(await _file_text(hass)))
    except (ValueError, TypeError, AttributeError, yaml.YAMLError):
        return None


def _agent_or_error(hass: HomeAssistant, connection, msg) -> Any | None:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    agent = entries[0].runtime_data.agent if entries else None
    if agent is None:
        connection.send_error(msg["id"], ERROR_NO_AGENT, "The Assist Router agent is not running")
    return agent


def _version(store: EditorStore, version: str) -> dict[str, Any] | None:
    return next((item for item in store.data["history"] if item["id"] == version), None)


def _summary(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: item.get(key) for key in ("id", "at", "by", "note")} for item in history]


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/editor/load"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_load(hass, connection, msg) -> None:
    """The file as it is, whether the router reads it, the draft and the history."""
    text = await _file_text(hass)
    store = _store(hass)
    connection.send_result(
        msg["id"],
        {
            "text": text,
            "hash": text_hash(text),
            "path": str(router_path(hass)),
            "check": check_text(text) if text else {"ok": False, "error": "missing", "topics": []},
            "draft": store.data["draft"],
            "history": _summary(store.data["history"]),
            "languages": available_languages(),
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/editor/check", vol.Required("text"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_check(hass, connection, msg) -> None:
    """Whether the router could read this text."""
    connection.send_result(msg["id"], await hass.async_add_executor_job(check_text, msg["text"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/save_draft",
        vol.Required("text"): str,
        vol.Required("base"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_draft(hass, connection, msg) -> None:
    """Keep the draft; `base` is the fingerprint of the file it was started from."""
    store = _store(hass)
    previous = store.data["draft"] or {}
    store.data["draft"] = {
        "text": msg["text"],
        "base": previous.get("base") or msg["base"],
        "updated_at": now_iso(),
        "by": _user(connection),
    }
    await store.async_save()
    draft = store.data["draft"]
    connection.send_result(msg["id"], {"updated_at": draft["updated_at"], "base": draft["base"]})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/editor/discard"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_discard(hass, connection, msg) -> None:
    store = _store(hass)
    store.data["draft"] = None
    await store.async_save()
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/save",
        vol.Required("base"): str,
        vol.Optional("force", default=False): bool,
        vol.Optional("note", default=""): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save(hass, connection, msg) -> None:
    """Write the draft to router.yaml: checked first, the old file kept in the history and .bak."""
    store = _store(hass)
    draft = store.data["draft"]
    if not draft:
        connection.send_error(msg["id"], ERROR_NO_DRAFT, "There is no draft to save")
        return
    check = await hass.async_add_executor_job(check_text, draft["text"])
    if not check["ok"]:
        connection.send_error(msg["id"], ERROR_INVALID, check["error"])
        return
    current = await _file_text(hass)
    if text_hash(current) != msg["base"] and not msg["force"]:
        connection.send_error(
            msg["id"], ERROR_CONFLICT, "router.yaml was changed elsewhere since the draft began"
        )
        return
    if current:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "text": current,
            "at": now_iso(),
            "by": _user(connection),
            "note": msg["note"],
        }
        store.data["history"] = [entry, *store.data["history"]][:HISTORY_LIMIT]
    await hass.async_add_executor_job(write_with_backup, router_path(hass), draft["text"])
    store.data["draft"] = None
    await store.async_save()
    connection.send_result(msg["id"], {"hash": text_hash(draft["text"]), "topics": check["topics"]})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/editor/history_get", vol.Required("version"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_history_get(hass, connection, msg) -> None:
    found = _version(_store(hass), msg["version"])
    if found is None:
        connection.send_error(msg["id"], ERROR_NOT_FOUND, "No such version")
        return
    connection.send_result(msg["id"], {"text": found["text"], "at": found["at"], "by": found["by"]})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/editor/restore", vol.Required("version"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_restore(hass, connection, msg) -> None:
    """A version of the history becomes the draft, never the file at once."""
    store = _store(hass)
    found = _version(store, msg["version"])
    if found is None:
        connection.send_error(msg["id"], ERROR_NOT_FOUND, "No such version")
        return
    current = await _file_text(hass)
    store.data["draft"] = {
        "text": found["text"],
        "base": text_hash(current),
        "updated_at": now_iso(),
        "by": _user(connection),
    }
    await store.async_save()
    connection.send_result(msg["id"], {"draft": store.data["draft"]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/sources",
        vol.Required("text"): str,
        vol.Required("topic"): str,
        vol.Optional("fetch", default=False): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_sources(hass, connection, msg) -> None:
    """What the data sources of a topic of this text give now; the services only with `fetch`."""
    try:
        config = parse_config(yaml.safe_load(msg["text"]))
    except (ValueError, TypeError, AttributeError, yaml.YAMLError) as err:
        connection.send_error(msg["id"], ERROR_INVALID, str(err))
        return
    topic = config.topics.get(msg["topic"])
    if topic is None:
        connection.send_error(msg["id"], ERROR_NOT_FOUND, "No such topic")
        return
    preview = await async_sources_preview(hass, config, topic, run_fetch=msg["fetch"])
    connection.send_result(msg["id"], preview)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/test",
        vol.Required("text"): str,
        vol.Required("sentence"): str,
        vol.Optional("speaker"): vol.Any(str, None),
        vol.Optional("persona"): vol.Any(str, None),
        vol.Optional("area"): vol.Any(str, None),
        vol.Optional("skip_ha", default=False): bool,
        vol.Optional("answer", default=True): bool,
        vol.Optional("compare", default=False): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_test(hass, connection, msg) -> None:
    """The way of a sentence on the text of the editor, without doing anything (tester.py)."""
    # tester uses the agent's module, which imports the integration: loaded only when used
    from .tester import TestOptions, async_trace

    config = _config_or_error(connection, msg, msg["text"])
    if config is None:
        return
    agent = _agent_or_error(hass, connection, msg)
    if agent is None:
        return
    saved = await _saved_config(hass) if msg["compare"] else None
    options = TestOptions(
        speaker=msg.get("speaker"),
        persona=msg.get("persona"),
        area=msg.get("area"),
        skip_ha=msg["skip_ha"],
        answer=msg["answer"],
    )
    trace = await async_trace(hass, agent, config, msg["sentence"], options, saved)
    connection.send_result(msg["id"], trace)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/editor/services"})
@websocket_api.require_admin
@callback
def websocket_services(hass, connection, msg) -> None:
    """The services a topic may fetch: those that only return data."""
    connection.send_result(msg["id"], read_only_services(hass))


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/editor/checks", vol.Required("text"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_checks(hass, connection, msg) -> None:
    """What is worth a look in the text before it is saved (preview.config_checks)."""
    config = _config_or_error(connection, msg, msg["text"])
    if config is None:
        return
    connection.send_result(msg["id"], {"checks": config_checks(hass, config)})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/editor/unrecognized"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_unrecognized(hass, connection, msg) -> None:
    """The log of unrecognized commands grouped by sentence, newest first."""
    rows = await CsvLog(hass, Path(hass.config.path(LOG_DIR, LOG_FILE))).async_rows()
    hidden = set(_store(hass).data["hidden"])
    groups = unrecognized_groups(rows, hidden)
    connection.send_result(msg["id"], {"groups": groups, "rows": len(rows)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/unrecognized_hide",
        vol.Required("key"): str,
        vol.Required("hidden"): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_unrecognized_hide(hass, connection, msg) -> None:
    """A sentence of the log hidden in the editor, or shown again; the log stays as it is."""
    store = _store(hass)
    hidden = [key for key in store.data["hidden"] if key != msg["key"]]
    if msg["hidden"]:
        hidden.append(msg["key"])
    store.data["hidden"] = hidden
    await store.async_save()
    connection.send_result(msg["id"], {"hidden": len(hidden)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/classify",
        vol.Required("text"): str,
        vol.Required("sentences"): [str],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_classify(hass, connection, msg) -> None:
    """Where sentences would go on the text of the editor: HA's intent or the router's topic."""
    config = _config_or_error(connection, msg, msg["text"])
    if config is None:
        return
    agent = _agent_or_error(hass, connection, msg)
    if agent is None:
        return
    found = await async_classify_sentences(hass, agent, config, msg["sentences"])
    connection.send_result(msg["id"], found)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/editor/tests_load"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_tests_load(hass, connection, msg) -> None:
    """The test set; a file that is not a test set is said, with nothing in it."""
    path = tests_path(hass)
    text = await hass.async_add_executor_job(read_text, path)
    try:
        tests, error = read_tests(text), None
    except (ValueError, yaml.YAMLError) as err:
        tests, error = [], str(err)
    connection.send_result(msg["id"], {"tests": tests, "path": str(path), "error": error})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/tests_save",
        vol.Required("tests"): [dict],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_tests_save(hass, connection, msg) -> None:
    """The test set written at once (the previous one kept as .bak)."""
    try:
        tests = [clean_test(item, index) for index, item in enumerate(msg["tests"])]
    except ValueError as err:
        connection.send_error(msg["id"], ERROR_INVALID, str(err))
        return
    await hass.async_add_executor_job(write_with_backup, tests_path(hass), dump_tests(tests))
    connection.send_result(msg["id"], {"tests": tests})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/tests_run",
        vol.Required("text"): str,
        vol.Optional("compare", default=True): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_tests_run(hass, connection, msg) -> None:
    """The test set on the text of the editor and on the saved file."""
    config = _config_or_error(connection, msg, msg["text"])
    if config is None:
        return
    agent = _agent_or_error(hass, connection, msg)
    if agent is None:
        return
    try:
        tests = read_tests(await hass.async_add_executor_job(read_text, tests_path(hass)))
    except (ValueError, yaml.YAMLError) as err:
        connection.send_error(msg["id"], ERROR_INVALID, str(err))
        return
    saved = await _saved_config(hass) if msg["compare"] else None
    connection.send_result(msg["id"], await async_run_tests(hass, agent, tests, config, saved))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/editor/sentences_load"})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_sentences_load(hass, connection, msg) -> None:
    """The files of custom_sentences and the intents Home Assistant can carry out."""
    files = await hass.async_add_executor_job(list_files, sentences_root(hass))
    language = hass.config.language.split("-")[0]
    languages = sorted({language, *(item["language"] for item in files)})
    connection.send_result(
        msg["id"],
        {
            "files": files,
            "languages": languages,
            "language": language,
            "intents": known_intents(hass),
        },
    )


async def _reload_sentences(hass: HomeAssistant, language: str) -> None:
    await hass.services.async_call("conversation", "reload", {"language": language}, blocking=True)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/sentences_save",
        vol.Required("language"): str,
        vol.Required("name"): str,
        vol.Required("text"): str,
        vol.Required("base"): str,
        vol.Optional("force", default=False): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_sentences_save(hass, connection, msg) -> None:
    """A file of sentences written (with .bak) and reloaded; `base` is the fingerprint of the
    file the change began from, "" for a new file."""
    path = file_path(sentences_root(hass), msg["language"], msg["name"])
    if path is None:
        connection.send_error(msg["id"], ERROR_INVALID, "Not a plain language or file name")
        return
    check = check_sentences(msg["text"])
    if not check["ok"]:
        connection.send_error(msg["id"], ERROR_INVALID, check["error"])
        return
    current = await hass.async_add_executor_job(read_text, path)
    if sentences_hash(current) != msg["base"] and current and not msg["force"]:
        connection.send_error(msg["id"], ERROR_CONFLICT, "The file was changed elsewhere")
        return
    await hass.async_add_executor_job(write_file, path, msg["text"])
    await _reload_sentences(hass, msg["language"])
    connection.send_result(
        msg["id"],
        {"hash": sentences_hash(msg["text"]), "check": check, "intents": known_intents(hass)},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/sentences_delete",
        vol.Required("language"): str,
        vol.Required("name"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_sentences_delete(hass, connection, msg) -> None:
    """A file of sentences put aside as .bak and the sentences reloaded without it."""
    path = file_path(sentences_root(hass), msg["language"], msg["name"])
    if path is None or not await hass.async_add_executor_job(path.is_file):
        connection.send_error(msg["id"], ERROR_NOT_FOUND, "No such file")
        return
    await hass.async_add_executor_job(remove_file, path)
    await _reload_sentences(hass, msg["language"])
    connection.send_result(msg["id"], {"removed": msg["name"]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/sentences_test",
        vol.Required("sentences"): [str],
        vol.Optional("language"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_sentences_test(hass, connection, msg) -> None:
    """What Home Assistant's own agent recognizes in sentences now, without running anything."""
    from .tester import _ha_summary, async_ha_debug

    results = []
    for sentence in msg["sentences"][:50]:
        found = await async_ha_debug(hass, sentence, msg.get("language"))
        results.append({"sentence": sentence, **_ha_summary(found)})
    connection.send_result(msg["id"], results)


COMMANDS = [
    websocket_load,
    websocket_check,
    websocket_save_draft,
    websocket_discard,
    websocket_save,
    websocket_history_get,
    websocket_restore,
    websocket_sources,
    websocket_services,
    websocket_test,
    websocket_checks,
    websocket_unrecognized,
    websocket_unrecognized_hide,
    websocket_classify,
    websocket_tests_load,
    websocket_tests_save,
    websocket_tests_run,
    websocket_sentences_load,
    websocket_sentences_save,
    websocket_sentences_delete,
    websocket_sentences_test,
    websocket_training_export,
    websocket_training_recordings,
    websocket_training_recording_files,
]
