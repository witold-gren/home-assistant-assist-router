"""The data sources of a topic in the editor: patterns with how many entities they find now, what the model
would get, attributes, and services with a response that are called only when asked."""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect
import yaml

FILE = """household: Tom
topics:
  home:
    description: the home
    entities:
      - "sensor.temp_*|temperature"
      - light.*   # every light
    skip_states: ["off"]
    details: [calendar.school]
  plan:
    description: the plan
    fetch:
      - action: calendar.get_events
        entities: calendar.*
"""
STATES = {
    "sensor.temp_room": {
        "state": "21.5",
        "attributes": {"device_class": "temperature", "friendly_name": "Room"},
    },
    "sensor.temp_wet": {"state": "40", "attributes": {"device_class": "humidity"}},
    "light.kitchen": {"state": "on", "attributes": {"friendly_name": "Kitchen"}},
    "light.bed": {"state": "off", "attributes": {"friendly_name": "Bed"}},
    "calendar.school": {
        "state": "off",
        "attributes": {"friendly_name": "School", "lesson": "maths"},
    },
}
SERVICES = {"calendar.get_events": "read_only", "light.turn_on": "changes"}
FETCHED = {"calendar.get_events": ["School: swimming at 10:00"]}


def open_editor(page: Page, **options) -> None:
    page.evaluate(
        "(options) => window.editor.open(options)",
        {"file": FILE, "states": STATES, "services": SERVICES, "fetched": FETCHED, **options},
    )
    page.locator("[data-node='topics/home']").click()


def text(page: Page) -> str:
    return page.evaluate("() => window.editor.app._text")


def sent(page: Page, kind: str) -> list[dict]:
    return page.evaluate(
        "(kind) => window.editor.server.state.sent.filter((m) => m.type === kind)",
        f"assist_router/editor/{kind}",
    )


def test_each_pattern_says_how_many_entities_it_finds(page: Page) -> None:
    open_editor(page)
    expect(page.locator("[data-count='sensor.temp_*|temperature']")).to_have_text("1")
    expect(page.locator("[data-count='light.*']")).to_have_text("2")
    expect(page.locator("[data-matched]")).to_contain_text(
        "Pasujące encje: 3; linie dla modelu: 2."
    )
    page.locator("[data-lines] summary").click()
    expect(page.locator("[data-lines] pre")).to_have_text("Room: 21.5\nKitchen: on")


def test_a_pattern_typed_is_counted_again_after_a_moment(page: Page) -> None:
    open_editor(page)
    add = page.locator("[data-list='topics/home/entities'] [data-add]")
    add.fill("switch.*")
    add.press("Enter")
    expect(page.locator("[data-count='switch.*']")).to_have_text("0")
    expect(page.locator("[data-count='switch.*']")).to_have_class(re.compile(r"\bzero\b"))
    # The comment beside the other pattern stays.
    assert "      - light.*   # every light\n      - switch.*\n" in text(page)


def test_the_attributes_for_the_model_are_shown(page: Page) -> None:
    open_editor(page)
    expect(page.locator("[data-count='calendar.school']")).to_have_text("1")
    page.locator("[data-details-preview] summary").click()
    expect(page.locator("[data-details-preview] pre")).to_contain_text("maths")


def test_services_are_fetched_only_with_the_button(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='topics/plan']").click()
    expect(page.locator("[data-fetch-item='0'] [data-count='calendar.*']")).to_have_text("1")
    assert not any(message.get("fetch") for message in sent(page, "sources"))
    page.locator("[data-run-fetch]").click()
    expect(page.locator("[data-fetched='0']")).to_contain_text("swimming")
    assert any(message.get("fetch") for message in sent(page, "sources"))


def test_a_service_is_added_changed_and_removed(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='topics/plan']").click()
    page.locator("[data-add-fetch]").click()
    fetch = lambda: yaml.safe_load(text(page))["topics"]["plan"]["fetch"]  # noqa: E731
    assert fetch()[1] == {"action": "calendar.get_events", "entities": []}
    action = page.locator("[data-field='topics/plan/fetch/1/action'] input")
    action.fill("light.turn_on")
    expect(page.locator("[data-field='topics/plan/fetch/1/action'] [data-warn]")).to_contain_text(
        "może coś zmienić"
    )
    title = page.locator("[data-field='topics/plan/fetch/1/title'] input")
    title.fill("Lights")
    page.locator("[data-field='topics/plan/fetch/1/past'] select").select_option("drop")
    data = page.locator("[data-field='topics/plan/fetch/1/data'] textarea")
    data.fill("type: [hourly")
    expect(page.locator("[data-field='topics/plan/fetch/1/data'] [data-warn]")).to_be_visible()
    data.fill("type: hourly")
    assert fetch()[1] == {
        "action": "light.turn_on",
        "entities": [],
        "title": "Lights",
        "past": "drop",
        "data": {"type": "hourly"},
    }
    page.locator("[data-remove-fetch='1']").click()
    assert len(fetch()) == 1


def test_the_services_that_read_are_suggested(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='topics/plan']").click()
    options = page.locator("assist-router-form").evaluate(
        "(form) => [...form.renderRoot.querySelectorAll('#services option')].map((o) => o.value)"
    )
    assert options == ["calendar.get_events"]


def test_a_text_the_router_cannot_read_stops_the_preview(page: Page) -> None:
    page.evaluate("(options) => window.editor.open(options)", {"file": FILE, "states": STATES})
    page.evaluate(
        """() => {
          const app = window.editor.app;
          const ask = app.hass.callWS;
          app.hass = { ...app.hass, callWS: (message) => message.type.endsWith("/sources")
            ? Promise.reject(new Error("personas: a map of names")) : ask(message) };
        }"""
    )
    page.locator("[data-node='topics/home']").click()
    expect(page.locator("[data-preview-error]")).to_contain_text("personas: a map of names")
