"""The pure parts of the editor: router.yaml as blocks of lines, so a change replaces one block and every
other line stays as it was; the tree of the file, the changes against it and the words of both languages."""

from __future__ import annotations

import pytest

EXAMPLES = ["router.example.pl.yaml", "router.example.yaml"]

FILE = """# Header of the file
# second line

household: >-
  Tom and Ann
# People in questions
people:
  tom: {name: Tom, match: "tom"}
  ann:
    name: Ann
announce_players:
- media_player.hall
- media_player.kitchen
topics:
  # The weather outside
  weather:
    description: the weather
    entities: [weather.home]
    examples: [Will it rain?]   # one is enough

  lights:
    description: lights
    control: true
  empty:
    examples: []
"""


def run(page, script: str, arg=None):
    return page.evaluate(f"async (arg) => {{ const e = window.editor; {script} }}", arg)


@pytest.mark.parametrize("name", EXAMPLES)
def test_every_block_of_the_examples_goes_back_unchanged(page, name: str) -> None:
    result = run(
        page,
        """
        const text = await e.fixture(arg);
        const { doc, error } = e.source.readDocument(text);
        const paths = e.source.keysAt(doc, []).map((key) => [key]);
        for (const key of ["topics", "people"]) paths.push(...e.source.keysAt(doc, [key]).map((child) => [key, child]));
        const changed = paths.filter((path) => {
          const block = e.source.blockText(text, path);
          return block !== null && e.source.replaceBlock(text, path, block).text !== text;
        });
        return { error, count: paths.length, changed };
        """,
        name,
    )
    assert result["error"] is None
    assert result["count"] > 20
    assert result["changed"] == []


def test_a_block_holds_the_comments_above_its_key_but_not_the_header(page) -> None:
    blocks = run(
        page,
        """
        const at = (path) => e.source.blockText(arg, path);
        return [at(["household"]), at(["people"]), at(["topics", "weather"]), at(["announce_players"])];
        """,
        FILE,
    )
    assert blocks[0] == "household: >-\n  Tom and Ann"
    assert blocks[1].startswith("# People in questions\npeople:\n")
    assert blocks[2] == (
        "# The weather outside\nweather:\n  description: the weather\n"
        "  entities: [weather.home]\n  examples: [Will it rain?]   # one is enough"
    )
    assert blocks[3] == "announce_players:\n- media_player.hall\n- media_player.kitchen"


def test_a_key_inside_braces_has_no_block_of_its_own(page) -> None:
    assert run(page, "return e.source.blockText(arg, ['people', 'tom', 'name']);", FILE) is None
    assert run(page, "return e.source.blockText(arg, ['people', 'missing']);", FILE) is None
    assert run(page, "return e.source.blockText(arg, ['people', 'tom']);", FILE) == (
        'tom: {name: Tom, match: "tom"}'
    )


def test_replacing_a_block_changes_only_its_lines(page) -> None:
    result = run(
        page,
        """
        const next = e.source.replaceBlock(arg, ["topics", "weather"], "weather:\\n  description: rain and sun");
        return { next: next.text, path: next.path };
        """,
        FILE,
    )
    before = FILE.split("\n")
    after = result["next"].split("\n")
    assert result["path"] == ["topics", "weather"]
    assert after[:14] == before[:14]
    assert after[14:16] == ["  weather:", "    description: rain and sun"]
    assert after[16:] == before[19:]


def test_a_new_key_renames_and_the_path_follows(page) -> None:
    path = run(
        page,
        "return e.source.replaceBlock(arg, ['topics', 'lights'], 'lamps:\\n  control: true').path;",
        FILE,
    )
    assert path == ["topics", "lamps"]


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("weather:\n  description: x", "unique"),
        ("lights:\n  examples: [a", "Flow sequence"),
        ("lights: 1\nmore: 2", "one_key"),
        ("# only a comment", "one_key"),
        ("- a list", "one_key"),
    ],
)
def test_a_block_that_does_not_fit_is_refused(page, snippet: str, message: str) -> None:
    error = run(
        page,
        """
        try { e.source.replaceBlock(arg.text, ["topics", "lights"], arg.snippet); return null; }
        catch (err) { return { message: err.message, yaml: err.yaml }; }
        """,
        {"text": FILE, "snippet": snippet},
    )
    assert error["yaml"] is True
    assert message in error["message"]


def test_removing_a_block_takes_one_empty_line_with_it(page) -> None:
    text = run(page, "return e.source.removeBlock(arg, ['topics', 'weather']);", FILE)
    assert "weather" not in text and "The weather outside" not in text
    assert "topics:\n\n  lights:" not in text
    assert "topics:\n  lights:" in text


@pytest.mark.parametrize(
    ("key", "left"),
    [
        ("a", "topics:\n  b:\n    x: 2\n\n  c:\n    x: 3\n"),
        ("b", "topics:\n  a:\n    x: 1\n\n  c:\n    x: 3\n"),
        ("c", "topics:\n  a:\n    x: 1\n\n  b:\n    x: 2\n"),
    ],
)
def test_topics_kept_apart_stay_apart_by_one_line(page, key: str, left: str) -> None:
    text = "topics:\n  a:\n    x: 1\n\n  b:\n    x: 2\n\n  c:\n    x: 3\n"
    assert (
        run(
            page,
            "return e.source.removeBlock(arg.text, ['topics', arg.key]);",
            {"text": text, "key": key},
        )
        == left
    )


def test_a_new_topic_goes_last_indented_as_the_others(page) -> None:
    result = run(
        page,
        "return e.source.appendBlock(arg, ['topics'], 'news:\\n  description: the news');",
        FILE,
    )
    assert result["path"] == ["topics", "news"]
    assert result["text"].endswith("    examples: []\n  news:\n    description: the news\n")


def test_topics_kept_apart_by_empty_lines_get_one_before_the_new(page) -> None:
    text = "topics:\n  a:\n    description: a\n\n  b:\n    description: b\n"
    result = run(
        page, "return e.source.appendBlock(arg, ['topics'], 'c:\\n  description: c').text;", text
    )
    assert result == text + "\n  c:\n    description: c\n"


@pytest.mark.parametrize("empty", ["topics:", "topics: {}", "topics:   # none yet"])
def test_an_empty_mapping_gets_its_first_child(page, empty: str) -> None:
    result = run(
        page,
        "return e.source.appendBlock(arg, ['topics'], 'a:\\n  description: a').text;",
        f"household: x\n{empty}\n",
    )
    comment = "   # none yet" if "#" in empty else ""
    assert (
        result
        == f"household: x\ntopics:{' # none yet' if comment else ''}\n  a:\n    description: a\n"
    )


def test_a_free_key_counts_up(page) -> None:
    keys = run(
        page,
        """
        const { doc } = e.source.readDocument(arg);
        return [e.source.freeKey(doc, ["topics"], "news"), e.source.freeKey(doc, ["topics"], "weather")];
        """,
        FILE + "  weather_2:\n    description: x\n",
    )
    assert keys == ["news", "weather_3"]


def test_the_tree_sorts_home_topics_and_special_ones(page) -> None:
    tree = run(
        page,
        """
        const { groups, error } = e.outline.buildOutline(arg, (key, values, fallback) => fallback ?? key);
        return { error, groups: groups.map((group) => ({ key: group.key, children: group.children.map((item) => ({
          key: item.key, kind: item.kind ?? null, warn: item.warn ?? null, block: item.block,
          missing: item.missing ?? false, children: item.children.map((child) => child.key) })) })) };
        """,
        FILE,
    )
    home, topics, special, learn = tree["groups"]
    assert [item["key"] for item in learn["children"]] == ["@unrecognized", "@tests"]
    assert [item["key"] for item in home["children"]] == [
        "household",
        "people",
        "family",
        "personas",
        "music_players",
        "announce_players",
        "confirm_entities",
        "@settings",
    ]
    assert [item["key"] for item in home["children"] if item["missing"]] == [
        "family",
        "personas",
        "music_players",
        "confirm_entities",
    ]
    assert home["children"][1]["children"] == ["people/tom", "people/ann"]
    assert [(item["key"], item["kind"]) for item in topics["children"]] == [
        ("topics/weather", "data")
    ]
    assert [(item["key"], item["kind"]) for item in special["children"]] == [
        ("topics/lights", "control"),
        ("topics/empty", "other"),
    ]
    assert special["children"][1]["warn"] == "warn_no_description"
    assert topics["children"][0]["warn"] is None


def test_the_settings_are_one_node_and_other_keys_follow_it(page) -> None:
    home = run(
        page,
        """
        const { groups } = e.outline.buildOutline(arg);
        return groups[0].children.slice(-2).map((item) => [item.key, item.block, item.children.map((c) => c.key)]);
        """,
        "sentences: 4\nextra: 1\ncontrol_model: answer\ntopics:\n  a:\n    description: a\n",
    )
    assert home == [["@settings", False, ["sentences", "control_model"]], ["extra", True, []]]


@pytest.mark.parametrize(
    ("topic", "kind"),
    [
        ({"control": True}, "control"),
        ({"unclear": True}, "unclear"),
        ({"search": "wikipedia"}, "knowledge"),
        ({"entities": ["sensor.*"]}, "data"),
        ({"fetch": [{"service": "weather.get_forecasts"}]}, "data"),
        ({"command": "news"}, "data"),
        ({"description": "chat"}, "other"),
        (None, "other"),
    ],
)
def test_the_kind_of_a_topic(page, topic, kind: str) -> None:
    assert run(page, "return e.outline.topicKind(arg);", topic) == kind


def test_the_tree_of_a_text_that_is_not_yaml_is_empty_with_the_error(page) -> None:
    result = run(
        page,
        "const o = e.outline.buildOutline(arg); return [o.error, o.groups.map((g) => g.children.length)];",
        "topics: [a",
    )
    assert result[0]
    # The nodes of learning read other files, so they stay.
    assert result[1] == [0, 0, 0, 2]


def test_a_search_keeps_the_parents_of_what_it_finds(page) -> None:
    keys = run(
        page,
        """
        const { groups } = e.outline.buildOutline(arg);
        return e.outline.flattenOutline(e.outline.filterOutline(groups, "tom")).map((item) => item.key);
        """,
        FILE,
    )
    assert keys == ["home", "people", "people/tom", "topics", "special", "learn"]


def test_the_changes_name_items_added_removed_and_changed(page) -> None:
    after = (
        FILE.replace("description: the weather", "description: rain")
        .replace("  empty:\n    examples: []\n", "  news:\n    description: news\n")
        .replace("household: >-\n  Tom and Ann\n", "")
    )
    changes = run(
        page,
        "return e.changes.describeChanges(arg.before, arg.after);",
        {"before": FILE, "after": after},
    )
    assert changes == {
        "added": ["topics/news"],
        "removed": ["household", "topics/empty"],
        "changed": ["topics/weather"],
        "other": False,
    }
    header = run(
        page,
        "return e.changes.describeChanges(arg, arg.replace('# second line', '# 2nd line'));",
        FILE,
    )
    assert header["other"] is True and header["changed"] == []


def test_the_diff_shows_changed_lines_with_their_numbers(page) -> None:
    hunks = run(
        page,
        "return e.changes.diffHunks(e.changes.diffLines(arg.a, arg.b), 1);",
        {"a": "a\nb\nc\nd\ne\nf", "b": "a\nb\nC\nd\ne\nf\ng"},
    )
    assert hunks == [
        {"kind": "skip", "count": 1},
        {"kind": "same", "text": "b", "line": 2},
        {"kind": "removed", "text": "c"},
        {"kind": "added", "text": "C", "line": 3},
        {"kind": "same", "text": "d", "line": 4},
        {"kind": "skip", "count": 1},
        {"kind": "same", "text": "f", "line": 6},
        {"kind": "added", "text": "g", "line": 7},
    ]


def test_both_languages_have_the_same_words(page) -> None:
    keys = run(page, "return e.i18n.LANGUAGES.map((language) => e.i18n.keysOf(language).sort());")
    assert keys[0] == keys[1]
    assert run(page, "return e.i18n.translate('pl-PL', 'check_ok', { count: 3 });") == (
        "Router czyta ten tekst. Tematów: 3."
    )
    assert run(page, "return e.i18n.translate('de', 'save_now');") == "Save"


def test_a_copy_of_a_block_gets_the_new_key_after_its_comments(page) -> None:
    copy = run(
        page, "return e.renameBlock(arg, 'weather_copy');", "# rain\nweather:\n  description: x"
    )
    assert copy == "# rain\nweather_copy:\n  description: x"
    quoted = run(page, "return e.renameBlock(arg, 'b');", '"a b":\n  x: 1')
    assert quoted == "b:\n  x: 1"
