"""Learning in the editor: the unrecognized sentences of the log (checked on the draft, made examples or topics,
tested, hidden) and the test set (added from the tester or by hand, run on the draft against the saved file)."""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect
import yaml

FILE = """household: Tom
topics:
  weather:
    description: the weather
    examples:
      - Will it rain?   # the most asked
  lights:
    description: lights
    control: true
    examples: ["Turn on the lamp"]
"""
LOG = [
    {
        "key": "do i need an umbrella",
        "text": "Do I need an umbrella?",
        "count": 3,
        "first": "2026-11-10 08:00:00",
        "last": "2026-11-12 09:00:00",
        "kinds": ["no_intent_match"],
        "speakers": ["Tom"],
        "areas": ["Hall"],
        "route": "other",
        "response": "",
    },
    {
        "key": "will it rain",
        "text": "Will it rain?",
        "count": 1,
        "first": "2026-11-11 10:00:00",
        "last": "2026-11-11 10:00:00",
        "kinds": ["no_intent_match"],
        "speakers": [],
        "areas": [],
        "route": "",
        "response": "",
    },
]


def open_editor(page: Page, **options) -> None:
    page.evaluate(
        "(options) => { localStorage.clear(); return window.editor.open(options); }",
        {"file": FILE, "log": LOG, "haKnows": ["Turn off the kitchen"], **options},
    )


def text(page: Page) -> str:
    return page.evaluate("() => window.editor.app._text")


def saved_tests(page: Page) -> list[dict]:
    return page.evaluate("() => window.editor.server.state.tests")


def group(page: Page, key: str):
    return page.locator(f"[data-log-sentence='{key}']")


def test_the_log_is_listed_by_sentence(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='@unrecognized']").click()
    expect(page.locator("[data-learn='unrecognized']")).to_be_visible()
    expect(group(page, "do i need an umbrella")).to_contain_text(
        "3× · ostatnio 2026-11-12 09:00:00"
    )
    expect(group(page, "do i need an umbrella")).to_contain_text("Wtedy: other")
    page.locator("[data-log-search]").fill("rain")
    expect(page.locator("[data-log-sentence]")).to_have_count(1)


def test_sentences_are_checked_on_the_draft(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='@unrecognized']").click()
    page.locator("[data-classify]").click()
    expect(group(page, "will it rain").locator("[data-outcome-of]")).to_contain_text("weather")
    expect(group(page, "do i need an umbrella").locator("[data-outcome-of]")).to_contain_text(
        "bez tematu"
    )
    group(page, "will it rain").locator("[data-open-topic]").click()
    expect(page.locator("[data-node='topics/weather']")).to_have_class(re.compile(r"\bsel\b"))


def test_a_sentence_becomes_an_example_and_the_comments_stay(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='@unrecognized']").click()
    group(page, "do i need an umbrella").locator("[data-add-example]").select_option("weather")
    assert "      - Will it rain?   # the most asked\n      - Do I need an umbrella?\n" in text(
        page
    )
    # once is enough
    group(page, "do i need an umbrella").locator("[data-add-example]").select_option("weather")
    assert text(page).count("Do I need an umbrella?") == 1
    page.wait_for_function("() => Boolean(window.editor.server.state.draft)")


def test_a_sentence_becomes_a_new_topic(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='@unrecognized']").click()
    group(page, "do i need an umbrella").locator("[data-new-topic]").click()
    topic = yaml.safe_load(text(page))["topics"]["do_i_need_an_umbrella"]
    assert topic == {
        "description": "Do I need an umbrella?",
        "examples": ["Do I need an umbrella?"],
    }
    expect(page.locator("[data-node='topics/do_i_need_an_umbrella']")).to_have_class(
        re.compile(r"\bsel\b")
    )
    expect(page.locator("[data-form='topic']")).to_be_visible()


def test_a_sentence_is_tested_and_hidden(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='@unrecognized']").click()
    group(page, "will it rain").locator("[data-try]").click()
    expect(page.locator("[data-sentence]")).to_have_value("Will it rain?")
    expect(page.locator("[data-outcome]")).to_be_visible()
    group(page, "will it rain").locator("[data-hide]").click()
    expect(group(page, "will it rain")).to_have_count(0)
    page.locator("[data-show-hidden]").check()
    expect(group(page, "will it rain")).to_have_class(re.compile(r"\bhidden\b"))
    assert page.evaluate("() => window.editor.server.state.hidden") == ["will it rain"]


def test_a_sentence_goes_to_the_tests_once_checked(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='@unrecognized']").click()
    button = group(page, "will it rain").locator("[data-to-tests]")
    expect(button).to_be_disabled()
    page.locator("[data-classify]").click()
    expect(button).to_be_enabled()
    button.click()
    page.wait_for_function("() => window.editor.server.state.tests.length === 1")
    assert saved_tests(page) == [{"sentence": "Will it rain?", "topic": "weather"}]


def test_the_tester_adds_a_test(page: Page) -> None:
    open_editor(page)
    page.locator("[data-sentence]").fill("Turn off the kitchen")
    page.locator("[data-sentence]").press("Enter")
    page.locator("[data-add-test]").click()
    expect(page.locator("[data-notice='ok']")).to_contain_text("Dodano do zestawu testów")
    assert saved_tests(page) == [{"sentence": "Turn off the kitchen", "intent": "HassTurnOn"}]
    page.locator("[data-add-test]").click()
    expect(page.locator("[data-notice='ok']")).to_contain_text("już jest")
    assert len(saved_tests(page)) == 1


def test_the_tests_run_on_the_draft_against_the_saved_file(page: Page) -> None:
    tests = [
        {"sentence": "Will it rain?", "topic": "weather"},
        {"sentence": "Is it cold?", "topic": "weather"},
        {"sentence": "Turn off the kitchen", "intent": "HassTurnOn"},
    ]
    open_editor(page, tests=tests)
    page.locator("[data-node='@tests']").click()
    expect(page.locator("[data-test]")).to_have_count(3)
    # the draft learns "Is it cold?" and forgets "Will it rain?"
    page.evaluate(
        "() => window.editor.app._setText(window.editor.app._text.replace('Will it rain?', 'Is it cold?'))"
    )
    page.locator("[data-run-tests]").click()
    expect(page.locator("[data-summary]")).to_contain_text("Zaliczone 2 z 3")
    expect(page.locator("[data-fixed]")).to_contain_text("Naprawione 1")
    expect(page.locator("[data-broken]")).to_contain_text("Popsute 1")
    expect(page.locator("[data-test='0'] [data-change='broken']")).to_be_visible()
    expect(page.locator("[data-test='1'] [data-change='fixed']")).to_be_visible()


def test_tests_are_added_changed_and_removed_and_saved_at_once(page: Page) -> None:
    open_editor(page, tests=[{"sentence": "Will it rain?", "topic": "weather"}])
    page.locator("[data-node='@tests']").click()
    page.locator("[data-new-sentence]").fill("Lights on")
    page.locator("[data-new-topic-select]").select_option("lights")
    page.locator("[data-new-test] button").click()
    page.wait_for_function("() => window.editor.server.state.tests.length === 2")
    page.locator("[data-test='0'] [data-test-expect]").select_option("@intent")
    page.wait_for_function("() => Boolean(window.editor.server.state.tests[0].intent)")
    assert saved_tests(page)[0] == {"sentence": "Will it rain?", "intent": "HassTurnOn"}
    page.locator("[data-test='0'] [data-remove-test]").click()
    page.wait_for_function("() => window.editor.server.state.tests.length === 1")
    assert saved_tests(page) == [{"sentence": "Lights on", "topic": "lights"}]
    # the test set is not a part of router.yaml
    assert text(page) == FILE


def test_the_learning_nodes_have_no_yaml(page: Page) -> None:
    open_editor(page)
    page.locator("[data-node='@tests']").click()
    page.locator("[data-tab='node']").click()
    expect(page.locator("[data-no-block='learn_no_block']")).to_be_visible()


def test_helpers_of_learning(page: Page) -> None:
    result = page.evaluate(
        """async () => {
          const learn = await import("/custom_components/assist_router/www/editor/learn.js");
          const text = "topics:\\n  a:\\n    examples: [x]\\n";
          return [
            learn.addExample(text, "a", "z"),
            learn.addExample(text, "a", "X"),
            learn.topicFromSentence(text, "A very long sentence that goes on and on and on").path,
            learn.testFrom("s", { topic: "a" }),
            learn.testFrom("s", { intent: "HassTurnOn" }),
            learn.testFrom("s", { topic: null }),
          ];
        }"""
    )
    assert result == [
        "topics:\n  a:\n    examples: [x, z]\n",
        "topics:\n  a:\n    examples: [x]\n",
        ["topics", "a_very_long_sentence_that_goes"],
        {"sentence": "s", "topic": "a"},
        {"sentence": "s", "intent": "HassTurnOn"},
        None,
    ]
