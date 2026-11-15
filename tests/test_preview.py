"""The preview of a topic's data sources in the editor: what each pattern finds, the lines the
answer model would get, and the services' answers only when asked and only from services that
just return data; nothing is switched."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, SupportsResponse
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.assist_router.const import DOMAIN
from custom_components.assist_router.preview import pattern_counts, read_only, read_only_services

TEXT = """household: Tom
only_exposed: false
topics:
  dom:
    description: dom
    entities: ["sensor.temp_*|temperature", "light.*", "!light.ipad_*"]
    skip_states: ["off"]
    details: [calendar.plan]
  plan:
    description: plan
    fetch:
      - action: calendar.get_events
        entities: calendar.*
        title: Wydarzenia
      - action: light.turn_on
        entities: light.*
"""


async def states(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.temp_salon", "21.5", {"device_class": "temperature", "friendly_name": "Salon"}
    )
    hass.states.async_set("sensor.temp_wilgoc", "40", {"device_class": "humidity"})
    hass.states.async_set("light.kuchnia", "on", {"friendly_name": "Kuchnia"})
    hass.states.async_set("light.sypialnia", "off", {"friendly_name": "Sypialnia"})
    hass.states.async_set("light.ipad_ekran", "on")
    hass.states.async_set("calendar.plan", "off", {"friendly_name": "Plan", "lekcja": "matematyka"})


async def ask(client, **message):
    await client.send_json_auto_id({"type": f"{DOMAIN}/editor/sources", **message})
    return await client.receive_json()


async def test_patterns_count_what_they_find_and_leave_out(hass: HomeAssistant, setup) -> None:
    await states(hass)
    counts = pattern_counts(hass, ("sensor.temp_*|temperature", "light.*", "!light.ipad_*"))
    assert [(c["pattern"], c["count"]) for c in counts] == [
        ("sensor.temp_*|temperature", 1),
        ("light.*", 3),
        ("!light.ipad_*", 1),
    ]
    assert counts[1]["sample"] == ["light.ipad_ekran", "light.kuchnia", "light.sypialnia"]


async def test_the_preview_gives_the_lines_of_the_model(hass, setup, hass_ws_client) -> None:
    await states(hass)
    client = await hass_ws_client(hass)
    answer = await ask(client, text=TEXT, topic="dom")
    assert answer["success"], answer
    entities = answer["result"]["entities"]
    # light.ipad_* left out; the light that is off matches, but skip_states leaves it out
    assert entities["matched"] == 3
    assert entities["lines"] == ["Salon: 21.5", "Kuchnia: włączone"]
    assert entities["only_exposed"] is False
    sources = answer["result"]["details"]["sources"]
    assert len(sources) == 1 and "matematyka" in sources[0]


async def test_services_are_called_only_when_asked_and_only_to_read(
    hass, setup, hass_ws_client
) -> None:
    await states(hass)
    events = async_mock_service(
        hass,
        "calendar",
        "get_events",
        response={"calendar.plan": {"events": [{"summary": "Basen", "start": "2026-11-13"}]}},
        supports_response=SupportsResponse.ONLY,
    )
    switched = async_mock_service(hass, "light", "turn_on")
    client = await hass_ws_client(hass)
    quiet = (await ask(client, text=TEXT, topic="plan"))["result"]["fetch"]
    assert [(f["action"], f["service"], f["sources"]) for f in quiet] == [
        ("calendar.get_events", "read_only", None),
        ("light.turn_on", "changes", None),
    ]
    assert events == []
    fetched = (await ask(client, text=TEXT, topic="plan", fetch=True))["result"]["fetch"]
    assert len(events) == 1
    assert "Basen" in fetched[0]["sources"][0]
    assert fetched[0]["targets"] == ["calendar.plan"]
    assert fetched[1]["sources"] is None
    assert switched == []


async def test_services_that_only_read_are_listed(hass: HomeAssistant, setup) -> None:
    async_mock_service(hass, "calendar", "get_events", supports_response=SupportsResponse.ONLY)
    async_mock_service(hass, "light", "turn_on")
    assert "calendar.get_events" in read_only_services(hass)
    assert "light.turn_on" not in read_only_services(hass)
    assert read_only(hass, "nothing.here") == "missing"


async def test_the_services_command(hass, setup, hass_ws_client) -> None:
    async_mock_service(hass, "weather", "get_forecasts", supports_response=SupportsResponse.ONLY)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/editor/services"})
    answer = await client.receive_json()
    assert "weather.get_forecasts" in answer["result"]


async def test_a_text_the_router_cannot_read_or_a_missing_topic(
    hass, setup, hass_ws_client
) -> None:
    client = await hass_ws_client(hass)
    bad = await ask(client, text="topics: [a", topic="dom")
    assert bad["error"]["code"] == "invalid"
    missing = await ask(client, text=TEXT, topic="nope")
    assert missing["error"]["code"] == "not_found"


async def test_only_administrators_see_the_preview(
    hass, setup, hass_ws_client, hass_admin_user
) -> None:
    hass_admin_user.groups = []
    client = await hass_ws_client(hass)
    answer = await ask(client, text=TEXT, topic="dom")
    assert answer["error"]["code"] == "unauthorized"


async def test_the_checks_before_saving(hass, setup, hass_ws_client) -> None:
    await states(hass)
    async_mock_service(hass, "calendar", "get_events", supports_response=SupportsResponse.ONLY)
    async_mock_service(hass, "light", "turn_on")
    text = TEXT.replace("household: Tom", "household: Tom\nanswer_prompt: 'Hi {household} {who}'")
    text += "  bez_opisu:\n    entities: [switch.nothing_*]\n"
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/editor/checks", "text": text})
    checks = (await client.receive_json())["result"]["checks"]
    found = {
        (c["level"], c["code"], c.get("topic"), c.get("pattern") or c.get("action")) for c in checks
    }
    assert ("error", "prompt", None, None) in found
    assert ("error", "fetch_changes", "plan", "light.turn_on") in found
    assert ("warn", "no_description", "bez_opisu", None) in found
    assert ("warn", "pattern_empty", "bez_opisu", "switch.nothing_*") in found
    assert ("warn", "no_examples", "dom", None) in found
    # a pattern that finds entities, and an exclusion, are fine
    assert not any(c.get("pattern") in ("light.*", "!light.ipad_*") for c in checks)
    prompt = next(c for c in checks if c["code"] == "prompt")
    assert prompt["problem"] == "{who}"


def test_a_prompt_the_router_cannot_fill() -> None:
    from custom_components.assist_router.preview import prompt_problem

    assert prompt_problem("") is None
    assert prompt_problem("Dom: {household}, {now}, {sentences}") is None
    assert prompt_problem("{who} and {x}") == "{who}, {x}"
    assert "expected" in prompt_problem("one { brace")
