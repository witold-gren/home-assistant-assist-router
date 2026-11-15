"""The forms of the editor in Chrome: a topic, the people, the family, the personas, music in rooms and the
settings. Each change writes one value and leaves the other lines of router.yaml as they were."""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect
import yaml

FILE = """# Router of the test home

household: Tom and Ann
people:
  tom:
    name: Tom
    match: "tom|dad"
  ann: Ann
music_players:
  Kitchen: [media_player.kitchen]
sentences: 4   # Wikipedia
topics:
  # Rain and sun
  weather:
    description: the weather
    entities: [weather.home]
    examples:
      - Will it rain?   # the most asked
      - Is it cold?

  lights:
    description: lights
    control: true
"""
STATES = {
    "weather.home": {},
    "media_player.kitchen": {},
    "media_player.hall": {},
    "switch.fridge": {},
}
AREAS = {
    "kitchen": {"area_id": "kitchen", "name": "Kitchen"},
    "hall": {"area_id": "hall", "name": "Hall"},
}


def open_editor(page: Page, **options) -> None:
    page.evaluate(
        "(options) => window.editor.open(options)",
        {"file": FILE, "states": STATES, "areas": AREAS, **options},
    )


def text(page: Page) -> str:
    return page.evaluate("() => window.editor.app._text")


def data(page: Page) -> dict:
    return yaml.safe_load(text(page))


def choose(page: Page, key: str) -> None:
    page.locator(f"[data-node='{key}']").click()


def field(page: Page, key: str):
    return page.locator(f"[data-field='{key}']").locator("input, textarea, select").first


def changed_lines(page: Page) -> list[tuple[str, str]]:
    before, after = FILE.split("\n"), text(page).split("\n")
    return [(a, b) for a, b in zip(before, after, strict=False) if a != b]


def test_a_topic_opens_in_its_form(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    expect(page.locator("[data-tab='form']")).to_have_class(re.compile(r"\bon\b"))
    expect(page.locator("[data-form='topic']")).to_be_visible()
    expect(page.locator("[data-key]")).to_have_value("weather")
    expect(field(page, "topics/weather/description")).to_have_value("the weather")
    rows = page.locator("[data-list='topics/weather/examples'] .row input:not([data-add])")
    expect(rows).to_have_count(2)
    expect(rows.first).to_have_value("Will it rain?")
    expect(page.locator("[data-kind-option='answer']")).to_have_class(re.compile(r"\bon\b"))
    expect(page.locator("[data-sources]")).to_contain_text("weather.home")


def test_typing_a_description_changes_its_line_and_is_one_step_to_undo(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    description = field(page, "topics/weather/description")
    description.fill("")
    description.press_sequentially("rain and sun", delay=5)
    assert changed_lines(page) == [
        ("    description: the weather", "    description: rain and sun")
    ]
    assert page.evaluate("() => window.editor.app._past.length") == 1
    page.wait_for_function("() => Boolean(window.editor.server.state.draft)")
    # Undo outside the field puts the old text back in the form too.
    page.locator("[data-undo]").click()
    assert text(page) == FILE
    expect(description).to_have_value("the weather")


def test_examples_are_added_changed_and_removed_with_their_comments_kept(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    examples = page.locator("[data-list='topics/weather/examples']")
    add = examples.locator("[data-add]")
    add.fill("Do I need an umbrella?")
    add.press("Enter")
    assert (
        "      - Will it rain?   # the most asked\n      - Is it cold?\n      - Do I need an umbrella?\n"
        in text(page)
    )
    examples.locator("[data-remove='1']").click()
    assert data(page)["topics"]["weather"]["examples"] == [
        "Will it rain?",
        "Do I need an umbrella?",
    ]
    assert "# the most asked" in text(page)
    examples.locator(".row input").first.fill("Will it snow?")
    assert data(page)["topics"]["weather"]["examples"][0] == "Will it snow?"


def test_an_empty_field_keeps_its_line_while_typed_and_goes_when_left(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    description = field(page, "topics/weather/description")
    description.fill("")
    assert '    description: ""' in text(page)
    description.blur()
    assert "description" not in data(page)["topics"]["weather"]
    expect(page.locator("[data-field='topics/weather/description'] [data-warn]")).to_be_visible()


def test_the_kind_of_a_topic_sets_its_flag_and_shows_its_fields(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-kind-option='knowledge']").click()
    assert data(page)["topics"]["weather"]["search"] == "wikipedia"
    expect(page.locator("[data-sources]")).to_have_count(0)
    expect(page.locator("[data-kind='knowledge']")).to_be_visible()
    page.locator("[data-kind-option='answer']").click()
    assert text(page) == FILE
    choose(page, "topics/lights")
    page.locator("[data-kind-option='answer']").click()
    assert "control" not in data(page)["topics"]["lights"]
    expect(page.locator("[data-kind='other']")).to_be_visible()


def test_answer_hints_for_kinds_of_speakers_and_one_person(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-hints] summary").click()
    field(page, "topics/weather/answer_hints/child").fill("Say it simply.")
    assert data(page)["topics"]["weather"]["answer_hints"] == {"child": "Say it simply."}
    page.locator("[data-add-hint]").select_option("ann")
    field(page, "topics/weather/answer_hints/ann").fill("Mention the umbrella.")
    assert data(page)["topics"]["weather"]["answer_hints"]["ann"] == "Mention the umbrella."
    field(page, "topics/weather/answer_hints/child").fill("")
    field(page, "topics/weather/answer_hints/ann").fill("")
    field(page, "topics/weather/answer_hints/ann").blur()
    # The hints left empty take the whole mapping out.
    assert "answer_hints" not in text(page)


def test_numbers_switches_and_days_of_a_topic(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    field(page, "topics/weather/answer_tokens").fill("300")
    page.locator("[data-field='topics/weather/personal'] input").check()
    page.locator("[data-days]").select_option("tomorrow")
    topic = data(page)["topics"]["weather"]
    assert (topic["answer_tokens"], topic["personal"], topic["days"]) == (300, True, "tomorrow")
    page.locator("[data-days]").select_option("#")
    page.locator("[data-days-count]").fill("14")
    page.locator("[data-days-count]").blur()
    assert data(page)["topics"]["weather"]["days"] == 14
    page.locator("[data-field='topics/weather/only_exposed'] select").select_option("false")
    assert data(page)["topics"]["weather"]["only_exposed"] is False
    page.locator("[data-field='topics/weather/personal'] input").uncheck()
    assert "personal" not in data(page)["topics"]["weather"]


def test_a_topic_renamed_in_the_form_moves_in_the_tree(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    key = page.locator("[data-key]")
    key.fill("lights")
    key.press("Enter")
    expect(page.locator("[data-rename-error]")).to_contain_text("zajęta")
    key.fill("Rain Now")
    key.press("Enter")
    expect(page.locator("[data-rename-error]")).to_contain_text("małe litery")
    key.fill("rain")
    key.press("Enter")
    expect(page.locator("[data-node='topics/rain']")).to_have_class(re.compile(r"\bsel\b"))
    assert text(page) == FILE.replace("  weather:", "  rain:")


def test_a_person_written_as_a_name_gets_fields_and_the_match_is_tried(page: Page) -> None:
    open_editor(page)
    choose(page, "people/ann")
    expect(field(page, "people/ann/name")).to_have_value("Ann")
    field(page, "people/ann/room").fill("Hall")
    assert data(page)["people"]["ann"] == {"name": "Ann", "room": "Hall"}
    field(page, "people/ann/match").fill("ann|mum")
    sample = page.locator("[data-sample]")
    sample.fill("Where is mum?")
    expect(page.locator("[data-sample-result='yes']")).to_contain_text("mum")
    sample.fill("Where is dad?")
    expect(page.locator("[data-sample-result='no']")).to_be_visible()
    field(page, "people/ann/match").fill("ann(")
    expect(page.locator("[data-field='people/ann/match'] [data-warn]")).to_be_visible()


def test_the_entities_of_a_person_are_suggested_from_home_assistant(page: Page) -> None:
    open_editor(page)
    choose(page, "people/tom")
    owns = page.locator("[data-list='people/tom/owns'] [data-add]")
    assert owns.get_attribute("list") == "entities"
    options = page.locator("assist-router-form").evaluate(
        "(form) => [...form.renderRoot.querySelectorAll('#players option')].map((o) => o.value)"
    )
    assert options == ["media_player.hall", "media_player.kitchen"]
    owns.fill("switch.fridge")
    owns.press("Enter")
    assert data(page)["people"]["tom"]["owns"] == ["switch.fridge"]


def test_a_person_is_added_from_the_list_and_opened(page: Page) -> None:
    open_editor(page)
    choose(page, "people")
    expect(page.locator("[data-entry]")).to_have_count(2)
    page.locator("[data-new-entry]").fill("Ola Łucja")
    page.locator("[data-new-entry]").press("Enter")
    expect(page.locator("[data-node='people/ola_lucja']")).to_have_class(re.compile(r"\bsel\b"))
    assert data(page)["people"]["ola_lucja"] == {"name": "Ola Łucja"}
    expect(page.locator("[data-form='person']")).to_be_visible()


def test_the_family_is_ticked_and_made_before_the_topics(page: Page) -> None:
    open_editor(page)
    choose(page, "family")
    expect(page.locator("[data-no-block]")).to_have_count(0)
    page.locator("[data-people='family/parents'] [data-person='tom']").check()
    page.locator("[data-people='family/parents'] [data-person='ann']").check()
    page.locator("[data-people='family/men'] [data-person='tom']").check()
    assert data(page)["family"] == {"parents": ["tom", "ann"], "men": ["tom"]}
    assert text(page).index("family:") < text(page).index("topics:")
    expect(page.locator("[data-node='family']")).not_to_have_class(re.compile(r"\bmissing\b"))


def test_a_persona_is_added_ready_for_the_router_and_warns_without_a_pipeline(page: Page) -> None:
    open_editor(page)
    choose(page, "personas")
    page.locator("[data-new-entry]").fill("Jarvis")
    page.locator("[data-new-entry]").press("Enter")
    persona = data(page)["personas"]["jarvis"]
    assert persona["pipelines"] == ["Jarvis"] and "Jarvis" in persona["prompt"]
    page.locator("[data-field='personas/jarvis/gender'] select").select_option("male")
    assert data(page)["personas"]["jarvis"]["gender"] == "male"
    page.locator("[data-list='personas/jarvis/pipelines'] [data-remove='0']").click()
    expect(page.locator("[data-list='personas/jarvis/pipelines'] [data-warn]")).to_be_visible()


def test_a_room_of_music_keeps_an_empty_list(page: Page) -> None:
    open_editor(page)
    choose(page, "music_players")
    page.locator("[data-new-entry]").fill("Hall")
    page.locator("[data-new-entry]").press("Enter")
    assert data(page)["music_players"]["Hall"] == []
    choose(page, "music_players/Kitchen")
    players = page.locator("[data-list='music_players/Kitchen']")
    players.locator("[data-remove='0']").click()
    assert data(page)["music_players"]["Kitchen"] == []


def test_the_settings_are_one_form(page: Page) -> None:
    open_editor(page)
    choose(page, "sentences")
    expect(page.locator("[data-form='settings']")).to_be_visible()
    field(page, "sentences").fill("6")
    assert "sentences: 6   # Wikipedia" in text(page)
    page.locator("[data-field='control_model'] select").select_option("answer")
    page.locator("[data-field='language'] select").select_option("pl")
    assert (data(page)["control_model"], data(page)["language"]) == ("answer", "pl")
    field(page, "answer_prompt").fill("Answer briefly. {household} {who}")
    expect(page.locator("[data-field='answer_prompt'] [data-warn]")).to_contain_text("{who}")
    expect(page.locator("[data-node='@settings'] ~ [data-node='answer_prompt']")).to_have_count(1)


def test_the_yaml_tab_is_kept_once_chosen(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-tab='node']").click()
    choose(page, "topics/lights")
    expect(page.locator("[data-node-yaml]")).to_be_visible()
    page.locator("[data-tab='form']").click()
    choose(page, "topics/weather")
    expect(page.locator("[data-form='topic']")).to_be_visible()
    # A node without lines of its own has no YAML to show.
    choose(page, "@settings")
    page.locator("[data-tab='node']").click()
    expect(page.locator("[data-no-block='settings_no_block']")).to_be_visible()


def test_a_value_the_text_cannot_take_says_why(page: Page) -> None:
    open_editor(page, file=FILE.replace("people:\n", "people: none\nold_people:\n"))
    choose(page, "people")
    page.locator("[data-new-entry]").fill("Ola")
    page.locator("[data-new-entry]").press("Enter")
    expect(page.locator("[data-form-error]")).to_be_visible()


def test_the_forms_speak_english(page: Page) -> None:
    open_editor(page, language="en")
    choose(page, "topics/weather")
    expect(page.locator("[data-tab='form']")).to_have_text("Form")
    expect(page.locator("[data-field='topics/weather/description']")).to_contain_text(
        "What it answers"
    )
