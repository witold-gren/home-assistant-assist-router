"""The values a form writes to router.yaml: only the lines of one value change, in the style of the file, with
the comments around them kept; what is written reads back in the router (PyYAML, YAML 1.1) as it was typed."""

from __future__ import annotations

import pytest
import yaml

EXAMPLES = ["router.example.pl.yaml", "router.example.yaml"]

FILE = """# Header of the file

household: Tom
sentences: 4   # how long
confirm_entities:
  - switch.a     # fridge
  # cameras
  - switch.cam
people:
  tom: {name: Tom, match: "tom"}
  ola: Ola
topics:
  weather:
    description: the weather
    examples: ["Will it rain?"]   # one is enough
  lights:
    control: true
"""


def run(page, script: str, arg=None):
    return page.evaluate(f"async (arg) => {{ const e = window.editor; {script} }}", arg)


def set_field(page, path: list[str], value, text: str = FILE):
    return run(
        page,
        """
        try { return e.fields.setField(arg.text, arg.path, arg.value === "<undefined>" ? undefined : arg.value); }
        catch (err) { return { error: err.message, yaml: err.yaml }; }
        """,
        {"text": text, "path": path, "value": value},
    )


def lines(text: str, start: int, end: int) -> list[str]:
    return text.split("\n")[start:end]


@pytest.mark.parametrize("name", EXAMPLES)
def test_every_value_of_the_examples_written_as_it_is_changes_nothing(page, name: str) -> None:
    changed = run(
        page,
        """
        const text = await e.fixture(arg);
        const { doc } = e.source.readDocument(text);
        const paths = e.source.keysAt(doc, []).filter((key) => key !== "topics").map((key) => [key]);
        for (const topic of e.source.keysAt(doc, ["topics"])) {
          paths.push(...e.source.keysAt(doc, ["topics", topic]).map((key) => ["topics", topic, key]));
        }
        for (const person of e.source.keysAt(doc, ["people"])) {
          paths.push(...e.source.keysAt(doc, ["people", person]).map((key) => ["people", person, key]));
        }
        return paths.filter((path) => e.fields.setField(text, path, e.source.valueAt(doc, path)) !== text);
        """,
        name,
    )
    assert changed == []


@pytest.mark.parametrize("name", EXAMPLES)
def test_new_texts_read_back_in_the_router_as_typed(page, name: str) -> None:
    """Every description and every list of examples of a file, changed by a form, as PyYAML reads them."""
    tricky = [
        "yes",
        "no",
        "on",
        "08",
        "2026-11-13",
        "a: b",
        "# not a comment",
        "ends with a colon:",
        "quotes \" and ' inside",
        "{braces} and [brackets]",
        "long " * 40,
    ]
    result = run(
        page,
        """
        let text = await e.fixture(arg.name);
        const topics = e.source.keysAt(e.source.readDocument(text).doc, ["topics"]);
        topics.forEach((topic, index) => {
          text = e.fields.setField(text, ["topics", topic, "description"], arg.tricky[index % arg.tricky.length].trim());
          text = e.fields.setField(text, ["topics", topic, "examples"], arg.tricky.slice(0, 1 + (index % 4)));
        });
        return { text, topics };
        """,
        {"name": name, "tricky": tricky},
    )
    data = yaml.safe_load(result["text"])
    for index, topic in enumerate(result["topics"]):
        assert data["topics"][topic]["description"] == tricky[index % len(tricky)].strip()
        assert data["topics"][topic]["examples"] == tricky[: 1 + (index % 4)]


def test_a_value_on_the_line_of_its_key_keeps_the_comment_beside_it(page) -> None:
    assert lines(set_field(page, ["sentences"], 6), 3, 4) == ["sentences: 6   # how long"]
    flow = set_field(page, ["topics", "weather", "examples"], ["Will it rain?", "Is it cold?"])
    assert lines(flow, 14, 15) == [
        '    examples: ["Will it rain?", "Is it cold?"]   # one is enough'
    ]


def test_a_list_of_lines_keeps_its_items_with_their_comments(page) -> None:
    text = set_field(page, ["confirm_entities"], ["switch.cam", "switch.new", "switch.a"])
    assert lines(text, 4, 9) == [
        "confirm_entities:",
        "  # cameras",
        "  - switch.cam",
        "  - switch.new",
        "  - switch.a     # fridge",
    ]
    assert lines(text, 9, 10) == ["people:"]


def test_a_list_at_the_indentation_of_its_key_stays_there(page) -> None:
    text = "players:\n- media_player.a\nother: 1\n"
    assert set_field(page, ["players"], ["media_player.a", "media_player.b"], text) == (
        "players:\n- media_player.a\n- media_player.b\nother: 1\n"
    )


def test_a_long_text_is_folded_and_a_folded_one_stays_folded(page) -> None:
    long = " ".join(["word"] * 30)
    text = set_field(page, ["topics", "weather", "description"], long)
    assert lines(text, 13, 16) == [
        "    description: >-",
        "      " + " ".join(["word"] * 19),
        "      " + " ".join(["word"] * 11),
    ]
    assert yaml.safe_load(text)["topics"]["weather"]["description"] == long
    again = set_field(page, ["topics", "weather", "description"], "short now", text)
    assert lines(again, 13, 15) == ["    description: >-", "      short now"]


def test_a_text_of_several_lines_keeps_them(page) -> None:
    text = set_field(page, ["household"], "Tom\nAnn")
    assert lines(text, 2, 5) == ["household: |-", "  Tom", "  Ann"]
    assert yaml.safe_load(text)["household"] == "Tom\nAnn"


def test_a_value_taken_out_goes_with_its_lines(page) -> None:
    text = set_field(page, ["topics", "weather", "examples"], "<undefined>")
    assert lines(text, 11, 16) == [
        "topics:",
        "  weather:",
        "    description: the weather",
        "  lights:",
        "    control: true",
    ]
    assert set_field(page, ["topics", "weather", "missing"], "<undefined>") == FILE


def test_a_new_value_goes_last_in_its_mapping(page) -> None:
    text = set_field(page, ["topics", "lights", "description"], "lights")
    assert text.endswith("  lights:\n    control: true\n    description: lights\n")


def test_a_new_mapping_inside_a_topic_is_made(page) -> None:
    text = set_field(page, ["topics", "weather", "answer_hints", "parent"], "short")
    assert lines(text, 14, 17) == [
        '    examples: ["Will it rain?"]   # one is enough',
        "    answer_hints:",
        "      parent: short",
    ]


def test_a_mapping_in_one_line_is_written_out_on_its_lines(page) -> None:
    text = set_field(page, ["people", "tom", "room"], "Tom's room")
    assert lines(text, 8, 14) == [
        "people:",
        "  tom:",
        "    name: Tom",
        "    match: tom",
        "    room: Tom's room",
        "  ola: Ola",
    ]


def test_a_value_under_a_text_is_refused(page) -> None:
    assert set_field(page, ["people", "ola", "room"], "x") == {"error": "not_a_map", "yaml": True}


def test_a_new_key_of_the_file_goes_before_the_topics(page) -> None:
    text = set_field(page, ["family", "parents"], ["tom"])
    assert lines(text, 9, 15) == [
        '  tom: {name: Tom, match: "tom"}',
        "  ola: Ola",
        "family:",
        "  parents: [tom]",
        "topics:",
        "  weather:",
    ]


def test_keys_kept_apart_by_empty_lines_get_one_before_the_new(page) -> None:
    text = "household: Tom\n\npeople:\n  tom: Tom\n\ntopics:\n  a:\n    description: a\n"
    assert set_field(page, ["sentences"], 3, text) == (
        "household: Tom\n\npeople:\n  tom: Tom\n\nsentences: 3\n\ntopics:\n  a:\n    description: a\n"
    )


def test_a_file_without_topics_gets_the_key_at_the_end(page) -> None:
    assert (
        set_field(page, ["sentences"], 3, "household: Tom\n") == "household: Tom\n\nsentences: 3\n"
    )


def test_a_key_is_renamed_in_place(page) -> None:
    result = run(
        page,
        "return e.fields.renameKey(arg, ['topics', 'weather'], 'rain');",
        FILE,
    )
    assert result["path"] == ["topics", "rain"]
    assert result["text"] == FILE.replace("  weather:", "  rain:")
    quoted = run(page, "return e.fields.renameKey(arg, ['people', 'ola'], 'yes').text;", FILE)
    assert '  "yes": Ola' in quoted


@pytest.mark.parametrize(("key", "error"), [("lights", "key_taken"), ("  ", "key_empty")])
def test_a_rename_to_a_taken_or_empty_name_is_refused(page, key: str, error: str) -> None:
    result = run(
        page,
        """
        try { return e.fields.renameKey(arg.text, ['topics', 'weather'], arg.key); }
        catch (err) { return err.message; }
        """,
        {"text": FILE, "key": key},
    )
    assert result == error


def test_keys_are_quoted_only_when_they_must_be(page) -> None:
    keys = run(page, "return ['Pokój Oli', 'yes', 'a: b', 'weather'].map(e.fields.yamlKey);")
    assert keys == ["Pokój Oli", '"yes"', '"a: b"', "weather"]


@pytest.mark.parametrize(
    ("kind", "flags"),
    [
        ("control", {"control": True}),
        ("unclear", {"unclear": True}),
        ("knowledge", {"search": "wikipedia"}),
        ("answer", {}),
    ],
)
def test_the_kind_of_a_topic_leaves_one_flag(page, kind: str, flags: dict) -> None:
    start = FILE.replace("    control: true\n", "    control: true\n    unclear: true\n")
    text = run(
        page,
        "return e.forms.setTopicKind(arg.text, ['topics', 'lights'], arg.kind);",
        {"text": start, "kind": kind},
    )
    topic = yaml.safe_load(text)["topics"]["lights"] or {}
    assert {key: topic[key] for key in ("control", "unclear", "search") if key in topic} == flags


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("Pokój Oli", "pokoj_oli"),
        ("Łukasz", "lukasz"),
        ("Hej Jarvis!", "hej_jarvis"),
        ("!!", "item"),
    ],
)
def test_a_key_is_made_of_a_name(page, name: str, key: str) -> None:
    assert run(page, "return e.forms.keyFromName(arg);", name) == key


@pytest.mark.parametrize(
    ("match", "name", "sample", "found"),
    [
        ("ol(a|i|ą|ę|u)\\b|olk", "Ola", "Daj to Olą i Oli", ["Olą", "Oli"]),
        ("ol(a|i|ą|ę|u)\\b", "Ola", "Olaf przyszedł", []),
        # Without a match: the first four letters of the name, so "Kubuś" is not found.
        ("", "Kuba", "Kuba i Kubuś", ["Kuba"]),
        ("tom|tat(a|y)\\b", "Tom", "Gdzie jest tata?", ["tata"]),
    ],
)
def test_the_match_of_a_person_is_tried_on_a_sentence(page, match, name, sample, found) -> None:
    result = run(
        page,
        "return e.forms.matchSample(arg.match, arg.name, arg.sample);",
        {"match": match, "name": name, "sample": sample},
    )
    assert result == {"found": found}


def test_a_bad_match_says_why(page) -> None:
    assert "error" in run(page, "return e.forms.matchSample('ol(a', 'Ola', 'Ola');")


def test_prompt_values_the_router_does_not_fill_are_found(page) -> None:
    values = run(
        page,
        "return e.forms.unknownPromptValues('Hi {household} at {now}, {who} and {}');",
    )
    assert values == ["who", ""]


@pytest.mark.parametrize(
    ("path", "form"),
    [
        (["topics", "a"], "topic"),
        (["topics"], None),
        (["topics", "a", "examples"], None),
        (["people"], "people"),
        (["people", "ola"], "person"),
        (["personas", "jarvis"], "persona"),
        (["music_players", "Salon"], "room"),
        (["@settings"], "settings"),
        (["sentences"], "settings"),
        (["extra"], None),
    ],
)
def test_which_nodes_have_a_form(page, path, form) -> None:
    assert run(page, "return e.forms.formFor(arg);", path) == form


FETCH = """topics:
  plan:
    fetch:
      # calendars
      - action: calendar.get_events   # all of them
        entities: calendar.*

      # weather
      - action: weather.get_forecasts
        entities: [weather.home]
    days: today
"""
CALENDARS = {"action": "calendar.get_events", "entities": "calendar.*"}
WEATHER = {"action": "weather.get_forecasts", "entities": ["weather.home"]}


def set_item(page, index: int, value, text: str = FETCH):
    return run(
        page,
        """
        const value = arg.value === "<undefined>" ? undefined : arg.value;
        return e.fields.setListItem(arg.text, ["topics", "plan", "fetch"], arg.index, value);
        """,
        {"text": text, "index": index, "value": value},
    )


def test_an_item_of_a_list_written_as_it_is_changes_nothing(page) -> None:
    assert set_item(page, 0, CALENDARS) == FETCH


def test_an_item_of_a_list_is_written_alone(page) -> None:
    text = set_item(page, 1, {**WEATHER, "title": "Forecast"})
    assert text == FETCH.replace(
        "        entities: [weather.home]\n",
        "        entities: [weather.home]\n        title: Forecast\n",
    )


def test_an_item_is_added_after_the_last(page) -> None:
    text = set_item(page, 2, {"action": "todo.get_items", "entities": "todo.*"})
    assert text == FETCH.replace(
        "    days: today",
        "      - action: todo.get_items\n        entities: todo.*\n    days: today",
    )


def test_an_item_goes_with_the_comments_over_it(page) -> None:
    assert set_item(page, 0, "<undefined>") == (
        "topics:\n  plan:\n    fetch:\n      # weather\n      - action: weather.get_forecasts\n"
        "        entities: [weather.home]\n    days: today\n"
    )


def test_the_last_item_takes_the_list_with_it(page) -> None:
    text = "topics:\n  plan:\n    fetch:\n      - action: a.b\n    days: today\n"
    assert set_item(page, 0, "<undefined>", text) == "topics:\n  plan:\n    days: today\n"


def test_a_list_missing_or_in_brackets_is_written_whole(page) -> None:
    text = "topics:\n  plan:\n    description: plan\n"
    assert set_item(page, 0, CALENDARS, text) == (
        text + "    fetch:\n      - action: calendar.get_events\n        entities: calendar.*\n"
    )
    flow = "topics:\n  plan:\n    fetch: [{action: a.b}]\n"
    assert yaml.safe_load(set_item(page, 1, CALENDARS, flow))["topics"]["plan"]["fetch"] == [
        {"action": "a.b"},
        CALENDARS,
    ]
