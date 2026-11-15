"""The editor of router.yaml in Chrome: the tree, editing one block or the whole file, the draft, undo, the
check, saving with a conflict, the history, and the parts of the window (columns, folding, the HA menu)."""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

FILE = """# Router of the test home

household: Tom and Ann
people:
  tom:
    name: Tom
topics:
  # Rain and sun
  weather:
    description: the weather
    entities: [weather.home]
    examples: [Will it rain?]

  lights:
    description: lights
    control: true
"""
WEATHER = (
    "# Rain and sun\nweather:\n  description: the weather\n  entities: [weather.home]\n"
    "  examples: [Will it rain?]"
)
EDITED = FILE.replace("description: the weather", "description: rain, sun and wind")
SELECTED = re.compile(r"\bsel\b")
OLD = FILE.replace("household: Tom and Ann", "household: Tom")


def open_editor(page: Page, **options) -> None:
    page.evaluate("(options) => window.editor.open(options)", {"file": FILE, **options})


def state(page: Page) -> dict:
    return page.evaluate("() => window.editor.server.state")


def text(page: Page) -> str:
    return page.evaluate("() => window.editor.app._text")


def wait_draft(page: Page, present: bool = True) -> None:
    page.wait_for_function(
        f"() => Boolean(window.editor.server.state.draft) === {str(present).lower()}"
    )


def choose(page: Page, key: str, yaml: bool = True) -> None:
    """A node of the tree, shown as YAML (the tests of the forms are in test_editor_forms.py)."""
    page.locator(f"[data-node='{key}']").click()
    if yaml:
        page.locator("[data-tab='node']").click()


def node_keys(page: Page) -> list[str]:
    return page.locator("[data-node]").evaluate_all(
        "(nodes) => nodes.map((node) => node.dataset.node)"
    )


def test_the_tree_shows_the_home_the_topics_and_the_special_ones(page: Page) -> None:
    open_editor(page)
    assert node_keys(page) == [
        "household",
        "people",
        "people/tom",
        "family",
        "personas",
        "music_players",
        "announce_players",
        "confirm_entities",
        "@settings",
        "topics/weather",
        "topics/lights",
        "@unrecognized",
        "@tests",
    ]
    # The parts of the home the file has none of yet are there to fill in.
    expect(page.locator("[data-node='family']")).to_have_class(re.compile(r"\bmissing\b"))
    expect(page.locator("[data-node='people']")).not_to_have_class(re.compile(r"\bmissing\b"))
    groups = page.locator("[data-group]").evaluate_all(
        "(items) => items.map((item) => item.textContent.trim())"
    )
    assert groups == ["Dom", "Tematy pytań", "Specjalne", "Nauka", "Komendy Home Assistanta"]
    expect(page.locator("[data-node='household']")).to_contain_text("Domownicy (opis)")
    expect(page.locator("[data-check='ok']")).to_contain_text("Tematów: 2")
    expect(page.locator("[data-path]")).to_have_text("/config/assist/router.yaml")
    expect(page.locator("[data-save]")).to_be_disabled()
    expect(page.locator("[data-pick]")).to_be_visible()


def test_a_topic_shows_its_block_with_the_comment_above_and_its_kind(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    expect(page.locator("[data-node-yaml]")).to_have_value(WEATHER)
    expect(page.locator("[data-node='topics/weather']")).to_have_class(SELECTED)
    expect(page.locator("[data-crumbs]")).to_have_text("topics › weather")
    expect(page.locator("[data-kind='data']")).to_contain_text("Dane domu")
    choose(page, "topics/lights")
    expect(page.locator("[data-kind='control']")).to_contain_text("Sterowanie")


def test_editing_a_block_changes_only_its_lines_and_keeps_a_draft(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-node-yaml]").fill(WEATHER.replace("the weather", "rain, sun and wind"))
    assert text(page) == EDITED
    expect(page.locator("[data-draft-state='draft']")).to_be_visible()
    wait_draft(page)
    assert state(page)["draft"]["text"] == EDITED
    assert state(page)["file"] == FILE
    expect(page.locator("[data-save]")).to_be_enabled()


def test_yaml_not_valid_yet_waits_and_says_why(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    area = page.locator("[data-node-yaml]")
    area.fill("weather:\n  examples: [a")
    expect(page.locator("[data-node-error]")).to_be_visible()
    assert text(page) == FILE
    area.fill("weather: 1\nrain: 2")
    expect(page.locator("[data-node-error]")).to_contain_text("dokładnie jeden klucz")
    area.fill(WEATHER.replace("the weather", "rain, sun and wind"))
    expect(page.locator("[data-node-error]")).to_have_count(0)
    assert text(page) == EDITED


def test_a_new_key_renames_the_topic_and_the_tree_follows(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-node-yaml]").fill(WEATHER.replace("weather:", "rain:"))
    expect(page.locator("[data-node='topics/rain']")).to_have_class(SELECTED)
    expect(page.locator("[data-crumbs]")).to_have_text("topics › rain")
    assert "  rain:\n" in text(page)


def test_undo_and_redo_go_back_and_forth_and_the_draft_follows(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-node-yaml]").fill(WEATHER.replace("the weather", "rain, sun and wind"))
    wait_draft(page)
    page.locator("[data-undo]").click()
    assert text(page) == FILE
    expect(page.locator("[data-node-yaml]")).to_have_value(WEATHER)
    # Back to the file as it is: the draft is dropped.
    wait_draft(page, present=False)
    expect(page.locator("[data-draft-state='clean']")).to_be_visible()
    page.locator("[data-redo]").click()
    assert text(page) == EDITED
    wait_draft(page)


def test_typing_in_one_block_is_one_step_to_undo(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    area = page.locator("[data-node-yaml]")
    area.click()
    # At the end of the comment over the key, where any letter keeps the YAML valid.
    area.evaluate("(field) => field.setSelectionRange(14, 14)")
    area.press_sequentially("x", delay=10)
    area.press_sequentially("yz", delay=10)
    assert page.evaluate("() => window.editor.app._past.length") == 1


def test_a_new_topic_is_added_last_chosen_and_ready_to_type(page: Page) -> None:
    open_editor(page)
    page.locator("[data-add-topic]").click()
    expect(page.locator("[data-node='topics/nowy_temat']")).to_have_class(SELECTED)
    assert text(page).endswith(
        "    control: true\n\n  nowy_temat:\n    description: na jakie pytania odpowiada ten temat\n"
        "    examples:\n      - Przykładowe pytanie?\n"
    )
    # The form of the new topic opens with its description ready to type.
    assert (
        page.evaluate(
            "() => window.editor.app.renderRoot.querySelector('assist-router-form')"
            ".renderRoot.activeElement?.closest('[data-field]')?.dataset.field"
        )
        == "topics/nowy_temat/description"
    )
    page.locator("[data-add-topic]").click()
    expect(page.locator("[data-node='topics/nowy_temat_2']")).to_be_visible()


def test_a_topic_is_added_to_a_file_without_topics(page: Page) -> None:
    open_editor(page, file="household: Tom\n")
    page.locator("[data-add-topic]").click()
    assert text(page).startswith("household: Tom\n\ntopics:\n  nowy_temat:\n")
    expect(page.locator("[data-check='ok']")).to_be_visible()


def test_a_topic_is_duplicated_with_its_comments(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-duplicate]").click()
    expect(page.locator("[data-node='topics/weather_kopia']")).to_have_class(SELECTED)
    assert text(page).count("# Rain and sun") == 2
    expect(page.locator("[data-check='ok']")).to_contain_text("Tematów: 3")


def test_deleting_asks_first_and_takes_the_comments_above(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.locator("[data-delete]").click()
    assert text(page) == FILE
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("[data-delete]").click()
    expect(page.locator("[data-node='topics/weather']")).to_have_count(0)
    assert "Rain and sun" not in text(page)
    assert "topics:\n  lights:" in text(page)
    expect(page.locator("[data-pick]")).to_be_visible()


def test_the_whole_file_is_edited_and_the_tree_reads_it(page: Page) -> None:
    open_editor(page)
    page.locator("[data-tab='file']").click()
    area = page.locator("[data-file-yaml]")
    expect(area).to_have_value(FILE)
    area.fill(FILE + "  news:\n    description: news\n")
    expect(page.locator("[data-node='topics/news']")).to_be_visible()
    area.fill("topics: [a")
    expect(page.locator("[data-file-error]")).to_be_visible()
    expect(page.locator("[data-tree-error]")).to_be_visible()
    expect(page.locator("[data-check='error']")).to_be_visible()
    expect(page.locator("[data-add-topic]")).to_have_count(0)


def test_the_check_says_when_the_router_would_not_read_the_text(page: Page) -> None:
    open_editor(page)
    page.locator("[data-tab='file']").click()
    page.locator("[data-file-yaml]").fill("household: Tom\n")
    expect(page.locator("[data-check='error']")).to_contain_text("no topics")


def test_saving_shows_the_changes_and_writes_the_file_with_a_note(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-node-yaml]").fill(WEATHER.replace("the weather", "rain, sun and wind"))
    page.locator("[data-save]").click()
    dialog = page.locator("[data-save-dialog]")
    expect(dialog.locator("[data-change='changed']")).to_have_text("weather")
    expect(dialog.locator("[data-diff] .added")).to_contain_text("description: rain, sun and wind")
    expect(dialog.locator("[data-diff] .removed")).to_contain_text("description: the weather")
    dialog.locator("[data-note]").fill("more weather")
    dialog.locator("[data-confirm]").click()
    expect(page.locator("[data-save-dialog]")).to_have_count(0)
    expect(page.locator("[data-notice='ok']")).to_contain_text("Zapisano")
    assert state(page)["file"] == EDITED
    assert state(page)["draft"] is None
    assert state(page)["history"][0]["note"] == "more weather"
    assert state(page)["history"][0]["text"] == FILE
    expect(page.locator("[data-draft-state='clean']")).to_be_visible()
    expect(page.locator("[data-undo]")).to_be_disabled()


def test_a_text_the_router_cannot_read_cannot_be_saved(page: Page) -> None:
    open_editor(page)
    page.locator("[data-tab='file']").click()
    page.locator("[data-file-yaml]").fill("household: Tom\n")
    page.locator("[data-save]").click()
    expect(page.locator("[data-invalid]")).to_contain_text("no topics")
    expect(page.locator("[data-confirm]")).to_be_disabled()
    page.keyboard.press("Escape")
    expect(page.locator("[data-save-dialog]")).to_have_count(0)


def test_a_file_changed_elsewhere_is_saved_only_when_asked_again(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-node-yaml]").fill(WEATHER.replace("the weather", "rain, sun and wind"))
    wait_draft(page)
    page.evaluate("() => { window.editor.server.state.file += '# by hand\\n'; }")
    page.locator("[data-save]").click()
    page.locator("[data-confirm]").click()
    expect(page.locator("[data-conflict]")).to_be_visible()
    assert state(page)["file"].endswith("# by hand\n")
    page.locator("[data-force]").click()
    expect(page.locator("[data-save-dialog]")).to_have_count(0)
    assert state(page)["file"] == EDITED
    saves = [
        message for message in state(page)["sent"] if message["type"] == "assist_router/editor/save"
    ]
    assert [save["force"] for save in saves] == [False, True]


def test_a_draft_begun_on_another_file_says_so_on_opening(page: Page) -> None:
    open_editor(
        page, draft={"text": EDITED, "base": "h-other", "updated_at": "2026-11-13T09:00:00+00:00"}
    )
    assert text(page) == EDITED
    expect(page.locator("[data-conflict-notice]")).to_be_visible()
    expect(page.locator("[data-draft-at]")).to_be_visible()
    expect(page.locator("[data-check='ok']")).to_be_visible()


def test_the_history_shows_a_version_against_the_file_and_restores_it(page: Page) -> None:
    history = [
        {
            "id": "v1",
            "text": OLD,
            "at": "2026-11-12T20:00:00+00:00",
            "by": "admin-id",
            "note": "first",
        }
    ]
    open_editor(page, history=history)
    page.locator("[data-history]").click()
    dialog = page.locator("[data-history-dialog]")
    expect(dialog.locator("[data-version='v1']")).to_contain_text("first")
    expect(dialog.locator("[data-version='v1']")).to_contain_text("Tomek")
    expect(dialog.locator("[data-restore]")).to_be_disabled()
    dialog.locator("[data-version='v1']").click()
    expect(dialog.locator("[data-diff] .added")).to_contain_text("household: Tom")
    dialog.locator("[data-restore]").click()
    expect(page.locator("[data-history-dialog]")).to_have_count(0)
    assert text(page) == OLD
    assert state(page)["draft"]["text"] == OLD
    assert state(page)["file"] == FILE
    expect(page.locator("[data-draft-state='draft']")).to_be_visible()


def test_restoring_over_a_draft_asks_first(page: Page) -> None:
    history = [
        {"id": "v1", "text": OLD, "at": "2026-11-12T20:00:00+00:00", "by": "admin-id", "note": ""}
    ]
    open_editor(
        page,
        history=history,
        draft={"text": EDITED, "base": "x", "updated_at": "2026-11-13T09:00:00+00:00"},
    )
    page.locator("[data-history]").click()
    page.locator("[data-version='v1']").click()
    expect(page.locator("[data-history-dialog] [data-restore]")).to_be_enabled()
    page.once("dialog", lambda dialog: dialog.dismiss())
    page.locator("[data-restore]").click()
    assert text(page) == EDITED


def test_an_empty_history_says_so(page: Page) -> None:
    open_editor(page)
    page.locator("[data-history]").click()
    expect(page.locator("[data-history-empty]")).to_be_visible()
    page.locator("[data-close]").click()
    expect(page.locator("[data-history-dialog]")).to_have_count(0)


def test_discarding_the_draft_asks_and_goes_back_to_the_file(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-node-yaml]").fill(WEATHER.replace("the weather", "rain, sun and wind"))
    wait_draft(page)
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("[data-discard]").click()
    wait_draft(page, present=False)
    expect(page.locator("[data-node-yaml]")).to_have_value(WEATHER)
    assert text(page) == FILE
    expect(page.locator("[data-discard]")).to_have_count(0)


def test_a_missing_file_is_made_by_saving(page: Page) -> None:
    open_editor(page, file="")
    expect(page.locator("[data-file-missing]")).to_be_visible()
    page.locator("[data-tab='file']").click()
    page.locator("[data-file-yaml]").fill(FILE)
    page.locator("[data-save]").click()
    page.locator("[data-confirm]").click()
    expect(page.locator("[data-notice='ok']")).to_be_visible()
    assert state(page)["file"] == FILE
    assert state(page)["history"] == []


def test_the_tree_folds_whole_and_remembers_it(page: Page) -> None:
    open_editor(page)
    page.locator("[data-fold-all]").click()
    expect(page.locator("[data-node='people/tom']")).to_have_count(0)
    open_editor(page)
    expect(page.locator("[data-node='people/tom']")).to_have_count(0)
    page.locator("[data-fold='people']").click()
    expect(page.locator("[data-node='people/tom']")).to_be_visible()
    page.locator("[data-fold-all]").click()
    page.locator("[data-unfold-all]").click()
    expect(page.locator("[data-node='people/tom']")).to_be_visible()


def test_a_search_narrows_the_tree(page: Page) -> None:
    open_editor(page)
    page.locator("[data-search]").fill("light")
    assert node_keys(page) == ["topics/lights"]
    page.locator("[data-search]").fill("")
    assert len(node_keys(page)) == 13


def test_the_side_columns_are_dragged_wider_and_remembered(page: Page) -> None:
    open_editor(page)
    bar = page.locator("[data-splitter='left']").bounding_box()
    page.mouse.move(bar["x"] + 3, bar["y"] + 200)
    page.mouse.down()
    page.mouse.move(bar["x"] + 103, bar["y"] + 200, steps=4)
    page.mouse.up()
    widths = page.evaluate("() => JSON.parse(localStorage.getItem('assist-router-editor-widths'))")
    assert 395 <= widths["left"] <= 405
    open_editor(page)
    assert page.locator("[data-tree]").bounding_box()["width"] == widths["left"]
    page.locator("[data-splitter='left']").dblclick()
    assert page.locator("[data-tree]").bounding_box()["width"] == 300


def test_the_menu_button_opens_the_sidebar_of_home_assistant(page: Page) -> None:
    open_editor(page)
    page.locator("[data-ha-menu]").click()
    assert page.evaluate("() => window.editor.events") == ["hass-toggle-menu"]


def test_keys_save_and_undo(page: Page) -> None:
    open_editor(page)
    choose(page, "topics/weather")
    page.locator("[data-node-yaml]").fill(WEATHER.replace("the weather", "rain, sun and wind"))
    page.locator("[data-node='household']").click()
    page.keyboard.press("Control+z")
    assert text(page) == FILE
    page.keyboard.press("Control+Shift+z")
    assert text(page) == EDITED
    page.keyboard.press("Control+s")
    expect(page.locator("[data-save-dialog]")).to_be_visible()


def test_tab_indents_by_two_spaces(page: Page) -> None:
    open_editor(page)
    page.locator("[data-tab='file']").click()
    area = page.locator("[data-file-yaml]")
    area.click()
    page.keyboard.press("Control+End")
    page.keyboard.press("Tab")
    expect(area).to_have_value(FILE + "  ")
    expect(area).to_be_focused()


def test_the_editor_speaks_english(page: Page) -> None:
    open_editor(page, language="en")
    expect(page.locator("h1")).to_have_text("Assist Router editor")
    expect(page.locator("[data-group='topics']")).to_contain_text("Topics of questions")
    expect(page.locator("[data-check='ok']")).to_contain_text(
        "The router reads this text: 2 topics."
    )


def test_the_look_follows_home_assistant_and_can_be_chosen(page: Page) -> None:
    page.evaluate("() => localStorage.removeItem('assist-router-editor-theme')")
    open_editor(page)
    app = page.locator("assist-router-editor-app")
    page.evaluate(
        "() => { window.editor.app.hass = { ...window.editor.app.hass, themes: { darkMode: true } }; }"
    )
    expect(app).to_have_attribute("data-theme", "dark")
    page.evaluate(
        "() => { window.editor.app.hass = { ...window.editor.app.hass, themes: { darkMode: false } }; }"
    )
    expect(app).to_have_attribute("data-theme", "light")
    button = page.locator("[data-theme-button]")
    button.click()  # auto → light
    expect(button).to_have_attribute("data-theme-button", "light")
    button.click()  # light → dark, whatever Home Assistant says
    expect(app).to_have_attribute("data-theme", "dark")
    assert page.evaluate("() => localStorage.getItem('assist-router-editor-theme')") == "dark"
    background = page.evaluate("() => getComputedStyle(window.editor.app).backgroundColor")
    button.click()  # dark → as Home Assistant (light now)
    expect(app).to_have_attribute("data-theme", "light")
    assert page.evaluate("() => getComputedStyle(window.editor.app).backgroundColor") != background


def test_the_look_of_the_system_when_home_assistant_says_nothing(page: Page) -> None:
    themes = page.evaluate("""async () => {
        const { editorTheme } = await import('/custom_components/assist_router/www/editor/editor-app.js');
        return [editorTheme('auto', {}, true), editorTheme('auto', {}, false), editorTheme('auto', { themes: { darkMode: false } }, true),
                editorTheme('dark', { themes: { darkMode: false } }, false), editorTheme('light', {}, true)];
    }""")
    assert themes == ["dark", "light", "light", "dark", "light"]


def test_a_group_of_the_tree_folds_and_remembers_it(page: Page) -> None:
    page.evaluate("() => localStorage.removeItem('assist-router-editor-collapsed')")
    open_editor(page)
    page.locator("[data-group-fold='topics']").click()
    assert "topics/weather" not in node_keys(page)
    assert "topics/lights" in node_keys(page)  # the special topics are another group
    assert "topics" in page.evaluate(
        "() => JSON.parse(localStorage.getItem('assist-router-editor-collapsed'))"
    )
    page.locator("[data-search]").fill("weather")
    assert node_keys(page) == ["topics/weather"]  # a search shows what it finds anyway
    page.locator("[data-search]").fill("")
    page.locator("[data-group='topics'] .group-name").click()
    assert "topics/weather" in node_keys(page)


def test_the_button_of_a_group_folds_everything_inside_it(page: Page) -> None:
    page.evaluate("() => localStorage.removeItem('assist-router-editor-collapsed')")
    open_editor(page)
    fold = page.locator("[data-group-fold-all='home']")
    expect(fold).to_have_attribute("data-open", "true")
    fold.click()
    keys = node_keys(page)
    assert "people" in keys and "people/tom" not in keys  # the group stays open, its parts fold
    expect(fold).to_have_attribute("data-open", "false")
    fold.click()
    assert "people/tom" in node_keys(page)
    # a group of single items folds itself
    page.locator("[data-group-fold-all='special']").click()
    assert "topics/lights" not in node_keys(page)
    page.locator("[data-group-fold-all='special']").click()
    assert "topics/lights" in node_keys(page)


def test_fold_all_keeps_the_groups_open(page: Page) -> None:
    page.evaluate("() => localStorage.removeItem('assist-router-editor-collapsed')")
    open_editor(page)
    page.locator("[data-fold-all]").click()
    keys = node_keys(page)
    assert "people" in keys and "people/tom" not in keys and "topics/weather" in keys
    page.locator("[data-unfold-all]").click()
    assert "people/tom" in node_keys(page)


def test_a_folded_group_opens_for_what_is_chosen_from_elsewhere(page: Page) -> None:
    page.evaluate("() => localStorage.removeItem('assist-router-editor-collapsed')")
    open_editor(page)
    page.locator("[data-group-fold='topics']").click()
    page.evaluate("() => window.editor.app._select({ path: ['topics', 'weather'] })")
    expect(page.locator("[data-node='topics/weather']")).to_have_class(SELECTED)
