"""Learning from what was said: the log of unrecognized commands grouped by sentence, sentences
hidden in the editor, the topic a draft would choose, and the test set run on the draft and on the
saved file."""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
import yaml

from custom_components.assist_router.const import COLUMNS, DOMAIN
from custom_components.assist_router.learn import (
    dump_tests,
    passes,
    read_tests,
    sentence_key,
    unrecognized_groups,
)

from .conftest import OLLAMA, ROUTER_YAML
from .test_control import _home
from .test_router import _answer

ROWS = [
    {"timestamp": "2026-11-10 08:00:00", "kind": "no_intent_match", "text": "Ile mam paliwa?",
     "route": "inne", "speaker": "Tomek", "area": "Salon"},
    {"timestamp": "2026-11-12 09:00:00", "kind": "no_valid_targets", "text": "ile mam paliwa",
     "route": "auto", "speaker": "Ania", "area": "Salon"},
    {"timestamp": "2026-11-11 10:00:00", "kind": "no_intent_match", "text": "Zaśpiewaj coś.",
     "route": "", "speaker": "", "area": ""},
]  # fmt: skip


def chat(aioclient_mock: AiohttpClientMocker, topics: dict[str, str]) -> None:
    async def handler(method, url, data):
        question = data["messages"][-1]["content"]
        topic = next((t for word, t in topics.items() if word in question), "inne")
        return AiohttpClientMockResponse(method, url, json=_answer(topic))

    aioclient_mock.post(f"{OLLAMA}/api/chat", side_effect=handler)


def write_log(hass: HomeAssistant, rows: list[dict]) -> None:
    path = Path(hass.config.path("assist", "unrecognized_commands.csv"))
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [";".join(COLUMNS)] + [";".join(row.get(c, "") for c in COLUMNS) for row in rows]
    path.write_text("﻿" + "\n".join(lines) + "\n", encoding="utf-8")


async def ok(client, **message):
    await client.send_json_auto_id({**message, "type": f"{DOMAIN}/editor/{message['type']}"})
    answer = await client.receive_json()
    assert answer["success"], answer
    return answer["result"]


def test_a_sentence_has_one_key_however_it_was_written() -> None:
    assert (
        sentence_key("  Ile mam  PALIWA?! ") == sentence_key("ile mam paliwa") == "ile mam paliwa"
    )


def test_the_log_is_grouped_by_sentence_newest_first() -> None:
    groups = unrecognized_groups(ROWS, {"zaśpiewaj coś"})
    assert [(g["text"], g["count"], g["hidden"]) for g in groups] == [
        ("ile mam paliwa", 2, False),
        ("Zaśpiewaj coś.", 1, True),
    ]
    fuel = groups[0]
    assert (fuel["first"], fuel["last"], fuel["route"]) == (
        "2026-11-10 08:00:00",
        "2026-11-12 09:00:00",
        "auto",
    )
    assert fuel["kinds"] == ["no_intent_match", "no_valid_targets"]
    assert fuel["speakers"] == ["Tomek", "Ania"]


def test_the_test_set_is_read_and_written() -> None:
    tests = [
        {"sentence": "Ile mam paliwa?", "topic": "auto"},
        {"sentence": "x", "intent": "HassTurnOn"},
    ]
    text = dump_tests(tests)
    assert text.startswith("# Test set")
    assert read_tests(text) == tests
    assert yaml.safe_load(text)["tests"][0] == {"sentence": "Ile mam paliwa?", "topic": "auto"}
    assert read_tests("") == []
    assert read_tests("- sentence: a\n  topic: b\n") == [{"sentence": "a", "topic": "b"}]


def test_a_file_that_is_no_test_set_is_refused() -> None:
    for text in ("tests: 3", "tests:\n  - topic: a\n"):
        try:
            read_tests(text)
        except ValueError:
            continue
        raise AssertionError(text)


def test_what_passes() -> None:
    assert passes({"sentence": "a", "topic": "auto"}, {"topic": "auto"})
    assert not passes({"sentence": "a", "topic": "auto"}, {"intent": "HassTurnOn"})
    assert passes({"sentence": "a", "intent": "HassTurnOn"}, {"intent": "HassTurnOn"})
    assert not passes({"sentence": "a"}, {"topic": "auto"})


async def test_the_log_and_hiding_in_the_editor(hass, router, hass_ws_client) -> None:
    write_log(hass, ROWS)
    client = await hass_ws_client(hass)
    loaded = await ok(client, type="unrecognized")
    assert loaded["rows"] == 3 and len(loaded["groups"]) == 2
    await ok(client, type="unrecognized_hide", key="zaśpiewaj coś", hidden=True)
    groups = (await ok(client, type="unrecognized"))["groups"]
    assert [g["hidden"] for g in groups] == [False, True]
    await ok(client, type="unrecognized_hide", key="zaśpiewaj coś", hidden=False)
    assert not any(g["hidden"] for g in (await ok(client, type="unrecognized"))["groups"])
    # the log itself is never changed
    csv = Path(hass.config.path("assist", "unrecognized_commands.csv")).read_text(encoding="utf-8")
    assert csv.count("\n") == 4


async def test_sentences_get_the_topic_of_the_draft(
    hass, router, aioclient_mock, hass_ws_client
) -> None:
    await _home(hass)
    chat(aioclient_mock, {"paliw": "auto"})
    client = await hass_ws_client(hass)
    found = await ok(
        client,
        type="classify",
        text=ROUTER_YAML,
        sentences=["ile mam paliwa", "włącz Lampa stojąca"],
    )
    assert found == [
        {"sentence": "ile mam paliwa", "topic": "auto"},
        {"sentence": "włącz Lampa stojąca", "intent": "HassTurnOn"},
    ]


async def test_the_test_set_is_saved_with_a_backup(hass, router, hass_ws_client) -> None:
    client = await hass_ws_client(hass)
    assert (await ok(client, type="tests_load"))["tests"] == []
    tests = [{"sentence": "ile mam paliwa", "topic": "auto"}]
    await ok(client, type="tests_save", tests=tests)
    await ok(client, type="tests_save", tests=[*tests, {"sentence": "zaśpiewaj", "topic": "inne"}])
    path = Path(hass.config.path("assist", "router_tests.yaml"))
    assert read_tests(path.with_name("router_tests.yaml.bak").read_text(encoding="utf-8")) == tests
    assert len((await ok(client, type="tests_load"))["tests"]) == 2
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/editor/tests_save", "tests": [{"topic": "auto"}]}
    )
    assert (await client.receive_json())["error"]["code"] == "invalid"


async def test_a_broken_test_file_is_said(hass, router, hass_ws_client) -> None:
    path = Path(hass.config.path("assist", "router_tests.yaml"))
    path.write_text("tests: 3\n", encoding="utf-8")
    client = await hass_ws_client(hass)
    loaded = await ok(client, type="tests_load")
    assert loaded["tests"] == [] and "tests" in loaded["error"]


async def test_the_tests_run_on_the_draft_and_the_saved_file(
    hass, router, aioclient_mock, hass_ws_client
) -> None:
    await _home(hass)
    chat(aioclient_mock, {"paliw": "paliwo", "pogod": "inne"})
    client = await hass_ws_client(hass)
    await ok(
        client,
        type="tests_save",
        tests=[
            {"sentence": "ile mam paliwa", "topic": "paliwo"},
            {"sentence": "jaka pogoda", "topic": "inne"},
            {"sentence": "włącz Lampa stojąca", "intent": "HassTurnOn"},
        ],
    )
    draft = ROUTER_YAML.replace("  auto:\n", "  paliwo:\n    description: paliwo\n  auto:\n")
    run = await ok(client, type="tests_run", text=draft)
    assert run["summary"] == {"total": 3, "passed": 3, "failed": 0, "fixed": 1, "broken": 0}
    fuel = run["results"][0]
    assert fuel["draft"] == {"topic": "paliwo"} and fuel["ok"] is True
    assert fuel["ok_saved"] is False  # the saved file has no such topic
    # the draft without the topic the tests expect
    worse = await ok(client, type="tests_run", text=ROUTER_YAML.replace("  inne:\n", "  reszta:\n"))
    assert worse["summary"]["broken"] == 1


async def test_only_administrators_learn(hass, router, hass_ws_client, hass_admin_user) -> None:
    hass_admin_user.groups = []
    client = await hass_ws_client(hass)
    for kind in ("unrecognized", "tests_load"):
        await client.send_json_auto_id({"type": f"{DOMAIN}/editor/{kind}"})
        assert (await client.receive_json())["error"]["code"] == "unauthorized"
