"""The router's editor on the server: the file as text with its comments, a draft that changes
nothing, saving that checks the text, keeps .bak and a history, and stops when the file was
changed elsewhere."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockUser

from custom_components.assist_router.const import DOMAIN
from custom_components.assist_router.editor import (
    HISTORY_LIMIT,
    PANEL_URL,
    STORAGE_KEY,
    WWW_DIR,
    resolve_static_file,
    text_hash,
)

FILE = """# Mój router
household: Tomek i Ania  # domownicy
topics:
  pogoda:
    description: pogoda na zewnątrz
    examples: ["Czy będzie padać?"]
  inne:
    description: wszystko inne
"""
DRAFT = FILE.replace("pogoda na zewnątrz", "pogoda i prognoza")


def router_file(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("assist", "router.yaml"))


@pytest.fixture
async def editor(hass: HomeAssistant, setup, hass_ws_client):
    path = router_file(hass)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FILE, encoding="utf-8")
    return await hass_ws_client(hass)


async def call(client, **message):
    await client.send_json_auto_id(message)
    return await client.receive_json()


async def ok(client, **message):
    answer = await call(client, **message)
    assert answer["success"], answer
    return answer["result"]


async def draft(client, text=DRAFT):
    loaded = await ok(client, type=f"{DOMAIN}/editor/load")
    return await ok(client, type=f"{DOMAIN}/editor/save_draft", text=text, base=loaded["hash"])


async def test_load_gives_the_file_with_its_comments_and_what_the_router_reads(editor) -> None:
    loaded = await ok(editor, type=f"{DOMAIN}/editor/load")
    assert loaded["text"] == FILE
    assert loaded["hash"] == text_hash(FILE)
    assert loaded["check"] == {"ok": True, "error": None, "topics": ["pogoda", "inne"]}
    assert (loaded["draft"], loaded["history"]) == (None, [])
    assert "pl" in loaded["languages"]


async def test_a_missing_file_is_said(hass, setup, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    loaded = await ok(client, type=f"{DOMAIN}/editor/load")
    assert loaded["text"] == "" and loaded["check"]["ok"] is False


async def test_check_says_what_the_router_cannot_read(editor) -> None:
    assert (await ok(editor, type=f"{DOMAIN}/editor/check", text="topics: [a"))["ok"] is False
    assert (await ok(editor, type=f"{DOMAIN}/editor/check", text=DRAFT))["ok"] is True


async def test_a_draft_changes_nothing_on_disk(hass, editor) -> None:
    await draft(editor)
    assert router_file(hass).read_text(encoding="utf-8") == FILE
    assert (await ok(editor, type=f"{DOMAIN}/editor/load"))["draft"]["text"] == DRAFT


async def test_saving_writes_the_draft_keeps_bak_and_history(hass, editor) -> None:
    await draft(editor)
    saved = await ok(editor, type=f"{DOMAIN}/editor/save", base=text_hash(FILE), note="opis pogody")
    assert saved["hash"] == text_hash(DRAFT) and saved["topics"] == ["pogoda", "inne"]
    path = router_file(hass)
    assert path.read_text(encoding="utf-8") == DRAFT
    assert path.with_name("router.yaml.bak").read_text(encoding="utf-8") == FILE
    loaded = await ok(editor, type=f"{DOMAIN}/editor/load")
    assert loaded["draft"] is None
    assert [item["note"] for item in loaded["history"]] == ["opis pogody"]
    old = await ok(editor, type=f"{DOMAIN}/editor/history_get", version=loaded["history"][0]["id"])
    assert old["text"] == FILE


async def test_a_text_the_router_cannot_read_is_not_saved(hass, editor) -> None:
    await draft(editor, "topics: [a")
    answer = await call(editor, type=f"{DOMAIN}/editor/save", base=text_hash(FILE))
    assert answer["error"]["code"] == "invalid"
    assert router_file(hass).read_text(encoding="utf-8") == FILE


async def test_a_file_changed_elsewhere_stops_saving_unless_forced(hass, editor) -> None:
    await draft(editor)
    router_file(hass).write_text(FILE + "# ręcznie\n", encoding="utf-8")
    answer = await call(editor, type=f"{DOMAIN}/editor/save", base=text_hash(FILE))
    assert answer["error"]["code"] == "conflict"
    await ok(editor, type=f"{DOMAIN}/editor/save", base=text_hash(FILE), force=True)
    assert router_file(hass).read_text(encoding="utf-8") == DRAFT


async def test_saving_without_a_draft_is_refused(editor) -> None:
    answer = await call(editor, type=f"{DOMAIN}/editor/save", base=text_hash(FILE))
    assert answer["error"]["code"] == "no_draft"


async def test_discard_and_restore(hass, editor) -> None:
    await draft(editor)
    await ok(editor, type=f"{DOMAIN}/editor/save", base=text_hash(FILE))
    version = (await ok(editor, type=f"{DOMAIN}/editor/load"))["history"][0]["id"]
    restored = await ok(editor, type=f"{DOMAIN}/editor/restore", version=version)
    assert restored["draft"]["text"] == FILE and restored["draft"]["base"] == text_hash(DRAFT)
    assert router_file(hass).read_text(encoding="utf-8") == DRAFT
    await ok(editor, type=f"{DOMAIN}/editor/discard")
    assert (await ok(editor, type=f"{DOMAIN}/editor/load"))["draft"] is None


async def test_the_history_keeps_the_newest_versions(hass, editor) -> None:
    for index in range(HISTORY_LIMIT + 2):
        text = FILE + f"# {index}\n"
        loaded = await ok(editor, type=f"{DOMAIN}/editor/load")
        await ok(editor, type=f"{DOMAIN}/editor/save_draft", text=text, base=loaded["hash"])
        await ok(editor, type=f"{DOMAIN}/editor/save", base=loaded["hash"])
    assert len((await ok(editor, type=f"{DOMAIN}/editor/load"))["history"]) == HISTORY_LIMIT


async def test_drafts_are_kept_in_storage(hass, editor, hass_storage) -> None:
    await draft(editor)
    await hass.async_block_till_done()
    assert hass_storage[STORAGE_KEY]["data"]["draft"]["text"] == DRAFT


async def test_people_who_are_not_administrators_cannot_edit(hass, editor, hass_ws_client) -> None:
    person = MockUser(name="Ola").add_to_hass(hass)
    refresh = await hass.auth.async_create_refresh_token(person, "client")
    token = hass.auth.async_create_access_token(refresh)
    ola = await hass_ws_client(hass, access_token=token)
    for message in (
        {"type": f"{DOMAIN}/editor/load"},
        {"type": f"{DOMAIN}/editor/save_draft", "text": DRAFT, "base": "x"},
        {"type": f"{DOMAIN}/editor/save", "base": "x"},
        {"type": f"{DOMAIN}/editor/restore", "version": "x"},
    ):
        assert (await call(ola, **message))["error"]["code"] == "unauthorized", message


async def test_the_panel_is_for_administrators_and_its_modules_are_served(
    hass, setup, hass_client_no_auth
) -> None:
    # The frontend starts before the first client, as the web server takes no routes after that.
    assert await async_setup_component(hass, "frontend", {})
    assert await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    panel = hass.data[DATA_PANELS][PANEL_URL]
    assert panel.require_admin is True
    assert "/editor/editor.js?v=" in panel.config["_panel_custom"]["module_url"]
    client = await hass_client_no_auth()
    response = await client.get("/assist_router_static/editor/editor.js")
    assert response.status == 200 and response.headers["Cache-Control"] == "no-cache"
    assert (await client.get("/assist_router_static/vendor/yaml.LICENSE")).status == 404


async def test_the_panel_leaves_the_sidebar_when_asked(hass, setup) -> None:
    assert await async_setup_component(hass, "frontend", {})
    assert await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DATA_PANELS][PANEL_URL].sidebar_title == "Edytor Assist Routera"
    # an option changed reloads the integration, which registers the panel again
    hass.config_entries.async_update_entry(
        setup, options={**setup.options, "editor_in_sidebar": False}
    )
    await hass.async_block_till_done()
    panel = hass.data[DATA_PANELS][PANEL_URL]
    assert (panel.sidebar_title, panel.sidebar_icon) == (None, None)
    assert panel.require_admin is True  # still at its address, for administrators


@pytest.mark.parametrize("path", ["../__init__.py", "../../manifest.json", "editor/../../const.py"])
def test_paths_outside_the_folder_are_refused(path: str) -> None:
    assert resolve_static_file(WWW_DIR, path) is None
