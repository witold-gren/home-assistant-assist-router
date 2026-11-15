"""Sentences of Home Assistant's own agent in the editor: custom_sentences/<language>/*.yaml checked
as Home Assistant reads them, written with a .bak, reloaded at once (a new sentence works without a
restart) and tested without running anything."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.assist_router.const import DOMAIN
from custom_components.assist_router.sentences import check_sentences, file_path, text_hash

from .test_control import _home

FILE = """language: pl
intents:
  HassTurnOn:
    data:
      - sentences:
          - "rozbudź {name}"
"""


async def call(client, **message):
    await client.send_json_auto_id({**message, "type": f"{DOMAIN}/editor/{message['type']}"})
    return await client.receive_json()


async def ok(client, **message):
    answer = await call(client, **message)
    assert answer["success"], answer
    return answer["result"]


def sentences_file(hass: HomeAssistant, name: str = "lampy.yaml") -> Path:
    return Path(hass.config.path("custom_sentences", "pl", name))


def test_a_file_is_checked_as_home_assistant_reads_it() -> None:
    check = check_sentences(FILE)
    assert check == {"ok": True, "error": None, "intents": [{"name": "HassTurnOn", "sentences": 1}]}
    assert check_sentences("")["ok"] is False
    assert "mapping" in check_sentences("- a")["error"]
    assert "data" in check_sentences("intents:\n  X: {}\n")["error"]
    assert "sentences" in check_sentences("intents:\n  X:\n    data: [{sentences: 3}]\n")["error"]
    bad = check_sentences(FILE.replace("rozbudź {name}", "rozbudź (to|tamto"))
    assert (
        bad["ok"] is False and "HassTurnOn" in bad["error"] and "rozbudź (to|tamto" in bad["error"]
    )
    assert check_sentences("intents: [a")["ok"] is False
    assert "responses" in check_sentences(FILE + "responses: 3\n")["error"]


@pytest.mark.parametrize(
    ("language", "name"),
    [
        ("pl", "../x.yaml"),
        ("../pl", "x.yaml"),
        ("pl", "x.txt"),
        ("pl", "a b.yaml"),
        ("p", "x.yaml"),
    ],
)
def test_names_that_leave_the_folder_are_refused(tmp_path, language: str, name: str) -> None:
    assert file_path(tmp_path, language, name) is None


def test_plain_names_are_taken(tmp_path) -> None:
    assert file_path(tmp_path, "pl", "lampy.yaml") == (tmp_path / "pl" / "lampy.yaml").resolve()
    assert file_path(tmp_path, "en-GB", "my_lights-2.yaml") is not None


async def test_a_new_sentence_works_at_once(hass, router, hass_ws_client) -> None:
    await _home(hass)
    client = await hass_ws_client(hass)
    before = await ok(client, type="sentences_test", sentences=["rozbudź Lampa stojąca"])
    assert before[0]["match"] is None
    await ok(client, type="sentences_save", language="pl", name="lampy.yaml", text=FILE, base="")
    assert sentences_file(hass).read_text(encoding="utf-8") == FILE
    after = await ok(client, type="sentences_test", sentences=["rozbudź Lampa stojąca"])
    assert after[0]["match"] is True
    assert (after[0]["intent"], after[0]["source"], after[0]["file"]) == (
        "HassTurnOn",
        "custom",
        "pl/lampy.yaml",
    )


async def test_testing_runs_nothing(hass, router, hass_ws_client) -> None:
    await _home(hass)
    calls = async_mock_service(hass, "light", "turn_on")
    client = await hass_ws_client(hass)
    await ok(client, type="sentences_save", language="pl", name="lampy.yaml", text=FILE, base="")
    await ok(client, type="sentences_test", sentences=["rozbudź Lampa stojąca"])
    await hass.async_block_till_done()
    assert calls == []
    assert hass.states.get("light.salon_lampa").state == "off"


async def test_load_lists_the_files_and_the_intents(hass, router, hass_ws_client) -> None:
    sentences_file(hass).parent.mkdir(parents=True, exist_ok=True)
    sentences_file(hass).write_text(FILE, encoding="utf-8")
    client = await hass_ws_client(hass)
    loaded = await ok(client, type="sentences_load")
    assert [(f["language"], f["name"], f["hash"]) for f in loaded["files"]] == [
        ("pl", "lampy.yaml", text_hash(FILE))
    ]
    assert loaded["files"][0]["check"]["ok"] is True
    assert "HassTurnOn" in loaded["intents"]
    assert loaded["language"] == "pl" and loaded["languages"] == ["pl"]


async def test_a_file_changed_elsewhere_is_saved_only_when_asked(
    hass, router, hass_ws_client
) -> None:
    client = await hass_ws_client(hass)
    await ok(client, type="sentences_save", language="pl", name="lampy.yaml", text=FILE, base="")
    sentences_file(hass).write_text(FILE + "# elsewhere\n", encoding="utf-8")
    changed = FILE.replace("rozbudź", "obudź")
    answer = await call(
        client,
        type="sentences_save",
        language="pl",
        name="lampy.yaml",
        text=changed,
        base=text_hash(FILE),
    )
    assert answer["error"]["code"] == "conflict"
    await ok(
        client,
        type="sentences_save",
        language="pl",
        name="lampy.yaml",
        text=changed,
        base=text_hash(FILE),
        force=True,
    )
    assert sentences_file(hass).read_text(encoding="utf-8") == changed
    bak = sentences_file(hass, "lampy.yaml.bak").read_text(encoding="utf-8")
    assert bak == FILE + "# elsewhere\n"


async def test_a_file_home_assistant_cannot_read_is_not_written(
    hass, router, hass_ws_client
) -> None:
    client = await hass_ws_client(hass)
    bad = FILE.replace("rozbudź {name}", "rozbudź [to")
    answer = await call(
        client, type="sentences_save", language="pl", name="lampy.yaml", text=bad, base=""
    )
    assert answer["error"]["code"] == "invalid"
    assert not sentences_file(hass).exists()
    answer = await call(
        client, type="sentences_save", language="pl", name="../x.yaml", text=FILE, base=""
    )
    assert answer["error"]["code"] == "invalid"


async def test_a_removed_file_stops_working(hass, router, hass_ws_client) -> None:
    await _home(hass)
    client = await hass_ws_client(hass)
    await ok(client, type="sentences_save", language="pl", name="lampy.yaml", text=FILE, base="")
    await ok(client, type="sentences_delete", language="pl", name="lampy.yaml")
    assert not sentences_file(hass).exists()
    assert sentences_file(hass, "lampy.yaml.bak").exists()
    after = await ok(client, type="sentences_test", sentences=["rozbudź Lampa stojąca"])
    assert after[0]["match"] is None
    answer = await call(client, type="sentences_delete", language="pl", name="lampy.yaml")
    assert answer["error"]["code"] == "not_found"


async def test_only_administrators_edit_sentences(
    hass, router, hass_ws_client, hass_admin_user
) -> None:
    hass_admin_user.groups = []
    client = await hass_ws_client(hass)
    answer = await call(client, type="sentences_load")
    assert answer["error"]["code"] == "unauthorized"
