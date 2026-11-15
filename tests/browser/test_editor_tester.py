"""The tester in the editor: a sentence on the draft, its way step by step, the options of who says it, the
sentences tried last and opening the topic it went to."""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

FILE = """household: Tom
people:
  tom: {name: Tom}
  ann: Ann
topics:
  weather:
    description: the weather
    entities: [weather.home]
    examples: ["Will it rain?"]
  lights:
    description: lights
    control: true
    examples: ["Turn on the lamp"]
"""
STATES = {"weather.home": {"state": "rainy", "attributes": {"friendly_name": "Home"}}}


def open_editor(page: Page, **options) -> None:
    page.evaluate(
        "(options) => { localStorage.clear(); return window.editor.open(options); }",
        {
            "file": FILE,
            "states": STATES,
            "haKnows": ["Turn off the kitchen"],
            "answers": {"weather": "Yes, take an umbrella."},
            **options,
        },
    )


def ask(page: Page, sentence: str) -> None:
    page.locator("[data-sentence]").fill(sentence)
    page.locator("[data-sentence]").press("Enter")


def sent_tests(page: Page) -> list[dict]:
    return page.evaluate(
        "() => window.editor.server.state.sent.filter((m) => m.type === 'assist_router/editor/test')"
    )


def test_a_question_shows_its_way_and_the_answer(page: Page) -> None:
    open_editor(page)
    ask(page, "Will it rain?")
    expect(page.locator("[data-outcome='answer']")).to_contain_text("Odpowiada router")
    expect(page.locator("[data-speech]")).to_have_text("„Yes, take an umbrella.”")
    expect(page.locator("[data-step='ha']")).to_contain_text("Nierozpoznane")
    expect(page.locator("[data-step='router'] [data-topic]")).to_have_text("weather")
    page.locator("[data-expand='data_lines'] summary").click()
    expect(page.locator("[data-expand='data_lines'] pre")).to_have_text("Home: rainy")


def test_the_draft_is_what_is_tested(page: Page) -> None:
    open_editor(page)
    page.evaluate(
        "() => window.editor.app._setText(window.editor.app._text.replace('Will it rain?', 'Is it wet?'))"
    )
    ask(page, "Is it wet?")
    expect(page.locator("[data-topic]")).to_have_text("weather")
    assert "Is it wet?" in sent_tests(page)[-1]["text"]


def test_a_sentence_home_assistant_knows_stops_there(page: Page) -> None:
    open_editor(page)
    ask(page, "Turn off the kitchen")
    expect(page.locator("[data-outcome='ha']")).to_be_visible()
    expect(page.locator("[data-step='router']")).to_have_count(0)


def test_control_is_shown_as_a_plan(page: Page) -> None:
    open_editor(page)
    ask(page, "Turn on the lamp")
    expect(page.locator("[data-outcome='control_execute']")).to_be_visible()
    expect(page.locator("[data-step='control']")).to_contain_text("Tylko plan")


def test_no_topic_goes_to_the_fallback(page: Page) -> None:
    open_editor(page)
    ask(page, "Sing a song")
    expect(page.locator("[data-outcome='fallback']")).to_contain_text("agent zapasowy")


def test_the_options_go_to_the_server(page: Page) -> None:
    open_editor(page)
    page.locator("[data-tester] .options summary").click()
    page.locator("[data-option='speaker']").select_option("ann")
    page.locator("[data-option='area']").fill("Kitchen")
    page.locator("[data-option='compare']").check()
    page.locator("[data-option='answer']").uncheck()
    ask(page, "Will it rain?")
    expect(page.locator("[data-outcome]")).to_be_visible()
    message = sent_tests(page)[-1]
    assert (message["speaker"], message["area"], message["compare"], message["answer"]) == (
        "ann",
        "Kitchen",
        True,
        False,
    )
    assert message["persona"] is None and message["skip_ha"] is False
    expect(page.locator("[data-saved-topic]")).to_contain_text("ten sam temat")


def test_the_topic_of_the_way_opens_in_the_form(page: Page) -> None:
    open_editor(page)
    ask(page, "Will it rain?")
    page.locator("[data-step='router'] [data-topic]").click()
    expect(page.locator("[data-node='topics/weather']")).to_have_class(re.compile(r"\bsel\b"))
    expect(page.locator("[data-form='topic']")).to_be_visible()


def test_the_sentences_tried_last_are_remembered(page: Page) -> None:
    open_editor(page)
    ask(page, "Will it rain?")
    expect(page.locator("[data-outcome]")).to_be_visible()
    ask(page, "Sing a song")
    expect(page.locator("[data-outcome='fallback']")).to_be_visible()
    ask(page, "Will it rain?")
    expect(page.locator("[data-outcome='answer']")).to_be_visible()
    recent = page.evaluate("() => JSON.parse(localStorage.getItem('assist-router-editor-tests'))")
    assert recent == ["Will it rain?", "Sing a song"]


def test_a_failure_of_the_server_is_said(page: Page) -> None:
    open_editor(page)
    page.evaluate(
        """() => {
          const app = window.editor.app;
          const ask = app.hass.callWS;
          app.hass = { ...app.hass, callWS: (message) => message.type.endsWith("/test")
            ? Promise.reject(new Error("The Assist Router agent is not running")) : ask(message) };
        }"""
    )
    ask(page, "Will it rain?")
    expect(page.locator("[data-tester-error]")).to_contain_text("agent is not running")


def test_the_last_sentences_keep_ten(page: Page) -> None:
    result = page.evaluate(
        """async () => {
          const { rememberSentence } = await import("/custom_components/assist_router/www/editor/tester.js");
          let recent = [];
          for (let i = 0; i < 12; i += 1) recent = rememberSentence(recent, `s${i}`);
          return [recent.length, recent[0], rememberSentence(recent, "  ")[0]];
        }"""
    )
    assert result == [10, "s11", "s11"]
