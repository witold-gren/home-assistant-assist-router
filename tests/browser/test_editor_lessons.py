"""The lessons of the editor (⚙ → Lessons): tasks in three parts (to start with, next steps, set up once), each a short
tour that goes where the task is done, frames one part at a time and can wait for the framed button to be clicked;
the list marks the ones gone through and says what a lesson still needs."""

from __future__ import annotations

from playwright.sync_api import Page, expect

from .test_editor_app import FILE, OLD, answer
from .test_editor_learn import LOG
from .test_editor_sentences import LIGHTS

TOUR = "assist-router-editor-tour"
LIST = "assist-router-lessons"
LESSONS = "/custom_components/assist_router/www/editor/lessons.js"
I18N = "/custom_components/assist_router/www/editor/i18n.js"
HISTORY = [
    {"id": "1", "at": "2026-11-12T10:00:00Z", "by": "admin-id", "note": "first", "text": OLD}
]
ORDER = [
    "first_topic",
    "data",
    "tester",
    "save",
    "unrecognized",
    "tests",
    "answer",
    "history",
    "command",
    "syntax",
    "home",
    "look",
]


def open_full(page: Page, **options) -> None:
    """The editor with everything a lesson can need: topics, a log, a test, a file of commands and a history."""
    page.evaluate(
        "(options) => window.editor.open(options)",
        {
            "file": FILE,
            "log": LOG,
            "tests": [{"sentence": "Will it rain?", "topic": "weather"}],
            "sentences": [{"language": "pl", "name": "lampy.yaml", "text": LIGHTS}],
            "history": HISTORY,
            **options,
        },
    )


def change(page: Page) -> None:
    page.evaluate("() => window.editor.app._setText(window.editor.app._text + '\\n# a change\\n')")


def open_lessons(page: Page) -> None:
    page.locator("[data-gear]").click()
    page.locator("[data-gear-lessons]").click()
    expect(page.locator(f"{LIST} [data-lessons-dialog]")).to_be_visible()


def start(page: Page, key: str) -> None:
    open_lessons(page)
    page.locator(f"{LIST} [data-lesson='{key}']").click()
    expect(page.locator(f"{TOUR} [data-tour-bubble]")).to_be_visible()


def step(page: Page) -> dict | None:
    return page.evaluate(
        """() => {
        const tour = document.querySelector('assist-router-editor-app').shadowRoot.querySelector('assist-router-editor-tour');
        if (!tour) return null;
        const root = tour.shadowRoot;
        const bubble = root.querySelector('[data-tour-bubble]');
        return { key: bubble.dataset.tourBubble, count: root.querySelector('[data-tour-count]').textContent.trim(),
                 title: bubble.querySelector('h3').textContent.trim(), text: bubble.querySelector('p').textContent.trim(),
                 frame: Boolean(root.querySelector('[data-tour-frame]')), waits: Boolean(root.querySelector('[data-tour-try]')) };
    }"""
    )


def wait_step(page: Page, key: str) -> None:
    page.wait_for_function(
        """(key) => {
        const tour = document.querySelector('assist-router-editor-app').shadowRoot.querySelector('assist-router-editor-tour');
        return tour?.shadowRoot.querySelector('[data-tour-bubble]')?.dataset.tourBubble === key;
    }""",
        arg=key,
    )


def next_step(page: Page) -> None:
    before = step(page)
    page.locator(f"{TOUR} [data-tour-next]").click()
    page.wait_for_function(
        """([key, count]) => {
        const tour = document.querySelector('assist-router-editor-app').shadowRoot.querySelector('assist-router-editor-tour');
        const root = tour?.shadowRoot;
        return !root || root.querySelector('[data-tour-count]')?.textContent.trim() !== count;
    }""",
        arg=[before["key"], before["count"]],
    )


def test_the_list_has_its_lessons_in_three_parts_and_says_what_one_needs(page: Page) -> None:
    open_full(page, sentences=[])
    open_lessons(page)
    keys = page.locator(f"{LIST} [data-lesson]").evaluate_all(
        "(rows) => rows.map((row) => row.dataset.lesson)"
    )
    assert keys == ORDER
    groups = page.locator(f"{LIST} [data-lessons-group]").all_inner_texts()
    assert [group.lower() for group in groups] == ["na początek", "następne kroki", "ustawiane raz"]
    assert "Pierwszy temat" in page.locator(f"{LIST} [data-lesson='first_topic']").inner_text()
    # No change in the draft: saving cannot be learnt yet, and the lesson says why; no intent of commands either,
    # but the lesson on a command makes its file itself
    save = page.locator(f"{LIST} [data-lesson='save']")
    expect(save).to_be_disabled()
    assert "zmiana w szkicu" in save.inner_text()
    syntax = page.locator(f"{LIST} [data-lesson='syntax']")
    expect(syntax).to_be_disabled()
    assert "Komenda Home Assistanta" in syntax.inner_text()
    expect(page.locator(f"{LIST} [data-lesson='command']")).to_be_enabled()
    # Esc closes the list
    page.keyboard.press("Escape")
    expect(page.locator(LIST)).to_have_count(0)


def test_a_lesson_waits_for_the_click_and_goes_where_the_task_is(page: Page) -> None:
    open_full(page)
    start(page, "first_topic")
    first = step(page)
    assert first["count"] == "Pierwszy temat · 1 z 6" and first["frame"] and first["waits"]
    # Next is not needed: the framed + makes the topic and the lesson goes on to its name
    page.locator("[data-add-topic]").click()
    wait_step(page, "name")
    selected = page.evaluate("window.editor.app._selected")
    assert selected[0] == "topics" and selected[1] not in ("weather", "lights")
    # The next steps frame the fields of the new topic
    for key in ["description", "examples", "kind", "side"]:
        next_step(page)
        now = step(page)
        assert now["key"] == key and now["frame"], key
    next_step(page)
    assert step(page) is None
    open_lessons(page)
    expect(page.locator(f"{LIST} [data-lesson='first_topic'] [data-lesson-done]")).to_have_count(1)


def test_outside_the_frame_nothing_takes_a_click_while_a_step_waits(page: Page) -> None:
    open_full(page)
    start(page, "first_topic")
    before = page.evaluate("window.editor.app._text")
    # The node of a topic, under a blocker: nothing is chosen and the lesson still waits
    page.mouse.click(120, 400)
    assert page.evaluate("window.editor.app._selected") is None
    assert page.evaluate("window.editor.app._text") == before
    assert step(page)["key"] == "add"


def test_escape_stops_a_lesson_and_it_is_not_marked_done(page: Page) -> None:
    open_full(page)
    start(page, "home")
    next_step(page)
    page.keyboard.press("Escape")
    expect(page.locator(TOUR)).to_have_count(0)
    assert page.evaluate("localStorage.getItem('assist-router-editor-lessons')") is None


def test_every_lesson_goes_through_without_an_error(page: Page) -> None:
    open_full(page)
    for key in ORDER:
        if key == "save":
            change(page)
        start(page, key)
        count = 0
        while (now := step(page)) is not None:
            count += 1
            assert now["frame"], f"{key}/{now['key']}: nothing framed"
            assert "lesson_" not in now["title"] and "lesson_" not in now["text"], (
                f"{key}/{now['key']}"
            )
            next_step(page)
        assert count > 2, key
        # A window the lesson opened (saving, the history) closed with it
        page.wait_for_function("() => !['save', 'history'].includes(window.editor.app._dialog)")
    done = page.evaluate("JSON.parse(localStorage.getItem('assist-router-editor-lessons'))")
    assert sorted(done) == sorted(ORDER)


def test_every_text_of_the_lessons_is_there_in_both_languages(page: Page) -> None:
    missing = page.evaluate(
        """async ([lessonsUrl, i18nUrl]) => {
        const { LESSONS, LESSON_GROUPS, NEEDS } = await import(lessonsUrl);
        const { translate } = await import(i18nUrl);
        const keys = ['lessons_title', 'lessons_lead', 'lessons_hint', 'lessons_steps', 'lessons_show', 'lesson_step', 'lesson_try',
                      ...LESSON_GROUPS.map(([heading]) => heading), ...Object.keys(NEEDS).map((need) => `lessons_needs_${need}`)];
        for (const lesson of LESSONS) {
          keys.push(`lesson_${lesson.key}_name`, `lesson_${lesson.key}_about`);
          for (const step of lesson.steps) keys.push(`lesson_${lesson.key}_${step.key}_title`, `lesson_${lesson.key}_${step.key}_text`);
        }
        // Every lesson is in one group of the list
        const grouped = LESSON_GROUPS.flatMap(([, list]) => list);
        const ungrouped = LESSONS.filter((lesson) => !grouped.includes(lesson.key)).map((lesson) => lesson.key);
        const absent = [];
        for (const language of ['en', 'pl'])
          for (const key of keys) if (translate(language, key, null, null) === null) absent.push(`${language}:${key}`);
        // The Polish words are Polish, not the English ones
        for (const key of keys) if (translate('pl', key) === translate('en', key) && !/^lesson_look_gear_title$/.test(key)) absent.push(`same:${key}`);
        return [...absent, ...ungrouped.map((key) => `group:${key}`)];
    }""",
        [LESSONS, I18N],
    )
    assert missing == []


def test_the_question_mark_offers_the_lesson_of_what_is_chosen(page: Page) -> None:
    open_full(page)
    page.locator("[data-node='@tests']").click()
    page.locator("[data-help='middle']").click()
    lesson = page.locator("[data-help-pop] [data-help-lesson]")
    expect(lesson).to_have_attribute("data-help-lesson", "tests")
    assert "Zestaw testów" in lesson.inner_text()
    lesson.click()
    expect(page.locator("[data-help-pop]")).to_have_count(0)
    wait_step(page, "node")
    assert step(page)["count"].startswith("Zestaw testów · 1 z ")
    # The "?" of the tree and of the right column have theirs
    page.keyboard.press("Escape")
    page.locator("[data-help='side']").click()
    expect(page.locator("[data-help-pop] [data-help-lesson]")).to_have_attribute(
        "data-help-lesson", "tester"
    )


def test_every_part_of_the_tree_has_its_lesson(page: Page) -> None:
    open_full(page)
    without = page.evaluate(
        """async (url) => {
        const { nodesWithoutLesson } = await import(url);
        const app = window.editor.app;
        return nodesWithoutLesson([...app._outline().groups, app._sentencesGroup()]);
    }""",
        LESSONS,
    )
    assert without == []


def test_the_lesson_on_saving_opens_the_window_and_closes_it_after(page: Page) -> None:
    open_full(page)
    change(page)
    start(page, "save")
    next_step(page)
    assert step(page)["waits"]
    page.locator("[data-save]").click()
    wait_step(page, "changes")
    assert page.evaluate("window.editor.app._dialog") == "save"
    page.keyboard.press("Escape")
    expect(page.locator(TOUR)).to_have_count(0)
    expect(page.locator("assist-router-save-dialog")).to_have_count(0)
    # Nothing was saved
    assert page.evaluate("window.editor.server.state.file") == FILE


def test_the_lesson_on_the_look_keeps_the_gear_window_open(page: Page) -> None:
    open_full(page)
    start(page, "look")
    page.locator("[data-gear]").click()
    wait_step(page, "theme")
    expect(page.locator("[data-gear-pop]")).to_be_visible()
    next_step(page)
    assert step(page)["key"] == "language"
    expect(page.locator("[data-gear-pop]")).to_be_visible()


def test_the_lessons_speak_english_too(page: Page) -> None:
    open_full(page, language="en")
    start(page, "tester")
    assert step(page)["count"] == "Try a sentence · 1 of 4"


def test_a_framed_part_scrolled_away_in_the_tree_is_brought_into_sight(page: Page) -> None:
    open_full(page)
    # The tree scrolled to its end: the + of the topics is cut off by the column, though inside the window
    page.evaluate(
        """() => { const tree = window.editor.app.renderRoot.querySelector('[data-tree]');
                   tree.style.maxHeight = '200px'; tree.style.overflow = 'auto'; tree.scrollTop = tree.scrollHeight; }"""
    )
    start(page, "first_topic")
    page.wait_for_function(
        """() => {
        const app = window.editor.app.renderRoot;
        const tree = app.querySelector('[data-tree]').getBoundingClientRect();
        const add = app.querySelector('[data-add-topic]').getBoundingClientRect();
        return add.top >= tree.top - 2 && add.bottom <= tree.bottom + 2;
    }"""
    )


def test_the_lesson_on_a_command_makes_the_first_file_without_writing_it(page: Page) -> None:
    open_full(page, sentences=[])
    start(page, "command")
    assert step(page)["waits"]
    # Next instead of the +: a new file with the usual name, chosen and not written to Home Assistant
    next_step(page)
    assert step(page)["key"] == "file" and step(page)["frame"]
    assert page.evaluate("window.editor.app._selected") == ["@sentences", "pl", "moje_komendy.yaml"]
    expect(page.locator("[data-sentences-state]")).to_contain_text("Nowy")
    assert page.evaluate("window.editor.server.state.sentences") == []


def test_the_plus_of_a_command_asks_for_the_name_and_the_lesson_goes_on_with_that_file(
    page: Page,
) -> None:
    open_full(page)
    start(page, "command")
    page.locator("[data-add-sentences]").click()
    answer(page, value="lampy_salon")
    wait_step(page, "file")
    assert page.evaluate("window.editor.app._selected") == ["@sentences", "pl", "lampy_salon.yaml"]
    # The intent step frames the form of the new file, not of the first one
    next_step(page)
    assert step(page)["key"] == "intent" and step(page)["frame"]


def test_esc_in_the_name_window_cancels_the_question_not_the_lesson(page: Page) -> None:
    open_full(page)
    start(page, "command")
    page.locator("[data-add-sentences]").click()
    expect(page.locator("[data-ask-input]")).to_be_focused()
    page.keyboard.press("Escape")
    expect(page.locator("[data-ask]")).to_have_count(0)
    assert step(page) is not None


def test_the_lesson_on_the_syntax_goes_from_the_form_to_yaml_and_back(page: Page) -> None:
    open_full(page)
    page.locator("[data-node='@tests']").click()
    start(page, "syntax")
    # It chose the file with an intent and frames where a sentence is typed
    wait_step(page, "words")
    assert page.evaluate("window.editor.app._selected")[0] == "@sentences"
    for key in ["slots", "group", "intent", "yaml"]:
        next_step(page)
        assert step(page)["key"] == key and step(page)["frame"], key
    assert step(page)["waits"]
    # The framed YAML button shows the file as text and the lesson frames it
    page.locator("assist-router-sentences [data-sentences-view='yaml']").click()
    wait_step(page, "lists")
    expect(page.locator("assist-router-sentences [data-sentences-yaml]")).to_be_visible()
    next_step(page)
    assert step(page)["key"] == "check" and step(page)["frame"]
    expect(page.locator("assist-router-sentences [data-add-intent]")).to_be_visible()
    next_step(page)
    assert step(page) is None
    # Nothing written: the file of commands is as it was
    assert page.evaluate("window.editor.server.state.sentences[0].text") == LIGHTS
