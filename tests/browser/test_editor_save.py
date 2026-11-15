"""The window of saving: what changes, what is worth a look (patterns that find nothing, services that change
things, topics without a description or examples) and the test set run on the draft, with what the change breaks."""

from __future__ import annotations

from playwright.sync_api import Page, expect

FILE = """household: Tom
topics:
  weather:
    description: the weather
    entities: [weather.home]
    examples: ["Will it rain?"]
  lights:
    description: lights
    control: true
"""
STATES = {"weather.home": {"state": "rainy", "attributes": {"friendly_name": "Home"}}}
TESTS = [
    {"sentence": "Will it rain?", "topic": "weather"},
    {"sentence": "Turn off the kitchen", "intent": "HassTurnOn"},
]


def open_editor(page: Page, **options) -> None:
    page.evaluate(
        "(options) => window.editor.open(options)",
        {
            "file": FILE,
            "states": STATES,
            "tests": TESTS,
            "haKnows": ["Turn off the kitchen"],
            **options,
        },
    )


def change(page: Page, old: str, new: str) -> None:
    page.evaluate(
        "([old, value]) => window.editor.app._setText(window.editor.app._text.replace(old, value))",
        [old, new],
    )


def open_save(page: Page) -> None:
    page.locator("[data-save]").click()
    expect(page.locator("[data-save-dialog]")).to_be_visible()


def test_a_clean_change_says_so(page: Page) -> None:
    open_editor(page)
    change(page, "the weather", "rain and sun")
    open_save(page)
    expect(page.locator("[data-checks='ok']")).to_be_visible()


def test_what_is_worth_a_look_is_listed(page: Page) -> None:
    open_editor(page)
    change(page, "    entities: [weather.home]", "    entities: [weather.home, sensor.nothing_*]")
    change(page, "  lights:", "  empty:\n    entities: [weather.home]\n  lights:")
    open_save(page)
    expect(page.locator("[data-check-item='pattern_empty']")).to_contain_text("sensor.nothing_*")
    expect(page.locator("[data-check-item='no_description']")).to_contain_text("empty")
    expect(page.locator("[data-check-item='no_examples']")).to_contain_text("empty")
    # warnings do not stop saving
    expect(page.locator("[data-confirm]")).to_be_enabled()


def test_the_tests_run_and_say_what_the_change_breaks(page: Page) -> None:
    open_editor(page)
    change(page, '["Will it rain?"]', '["Is it wet?"]')
    open_save(page)
    page.locator("[data-run-tests]").click()
    expect(page.locator("[data-tests-summary]")).to_contain_text("Zaliczone 1 z 2")
    expect(page.locator("[data-tests-broken]")).to_contain_text("psuje")
    expect(page.locator("[data-tests-failed]")).to_contain_text("Will it rain?")
    expect(page.locator("[data-confirm]")).to_be_enabled()
    sent = page.evaluate(
        "() => window.editor.server.state.sent.filter((m) => m.type.endsWith('/tests_run'))"
    )
    assert sent[-1]["compare"] is True and "Is it wet?" in sent[-1]["text"]


def test_tests_of_a_topic_gone_are_said(page: Page) -> None:
    open_editor(page)
    change(page, "  weather:", "  rain:")
    open_save(page)
    expect(page.locator("[data-tests-missing]")).to_contain_text("weather")


def test_without_tests_the_way_to_add_them_is_said(page: Page) -> None:
    open_editor(page, tests=[])
    change(page, "the weather", "rain and sun")
    open_save(page)
    expect(page.locator("[data-tests='none']")).to_contain_text("Nauka")


def test_a_text_the_router_cannot_read_shows_only_why(page: Page) -> None:
    open_editor(page)
    change(page, "topics:", "topics: 1\nold:")
    open_save(page)
    expect(page.locator("[data-invalid]")).to_be_visible()
    expect(page.locator("[data-checks]")).to_have_count(0)


def test_the_checks_are_not_available_without_the_server(page: Page) -> None:
    open_editor(page)
    page.evaluate(
        """() => {
          const app = window.editor.app;
          const ask = app.hass.callWS;
          app.hass = { ...app.hass, callWS: (message) => message.type.endsWith("/checks")
            ? Promise.reject(new Error("offline")) : ask(message) };
        }"""
    )
    change(page, "the weather", "rain and sun")
    open_save(page)
    expect(page.locator("[data-checks='unavailable']")).to_be_visible()
