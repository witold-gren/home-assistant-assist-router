"""The tour of the editor: on the first visit it shows the parts of the screen one at a time (framed, the rest dimmed,
a bubble that says what it is and where it is set), skipped once it stays away, ⚙ brings it back."""

from __future__ import annotations

from playwright.sync_api import Page, expect

from .test_editor_app import open_editor

TOUR = "assist-router-editor-tour"
STEPS = ["welcome", "tree", "add", "middle", "tabs", "side", "tester", "undo", "save", "help"]


def step(page: Page) -> dict:
    return page.evaluate(
        """() => {
        const tour = document.querySelector('assist-router-editor-app').shadowRoot.querySelector('assist-router-editor-tour');
        if (!tour) return null;
        const root = tour.shadowRoot;
        const bubble = root.querySelector('[data-tour-bubble]');
        const frame = root.querySelector('[data-tour-frame]');
        const box = bubble.getBoundingClientRect();
        return { key: bubble.dataset.tourBubble, count: root.querySelector('[data-tour-count]').textContent.trim(),
                 title: bubble.querySelector('h3').textContent.trim(), text: bubble.querySelector('p').textContent.trim(),
                 frame: frame ? frame.getBoundingClientRect().toJSON() : null,
                 bubble: box.toJSON() };
    }"""
    )


def next_step(page: Page) -> None:
    before = step(page)["key"]
    page.locator(f"{TOUR} [data-tour-next]").click()
    page.wait_for_function(
        """(before) => {
        const tour = document.querySelector('assist-router-editor-app').shadowRoot.querySelector('assist-router-editor-tour');
        return !tour || tour.shadowRoot.querySelector('[data-tour-bubble]')?.dataset.tourBubble !== before;
    }""",
        arg=before,
    )


def topic(page: Page) -> None:
    page.locator("[data-node='topics/weather']").click()


def test_the_first_time_the_editor_shows_itself_round(page: Page) -> None:
    open_editor(page, tour=True)
    expect(page.locator(f"{TOUR} [data-tour-bubble]")).to_be_visible()
    first = step(page)
    assert first["key"] == "welcome" and first["frame"] is None
    assert first["title"] == "Witaj w edytorze"
    assert first["count"].lower().startswith("przewodnik · 1 z ")


def test_every_step_frames_its_part_and_the_last_one_ends_it(page: Page) -> None:
    open_editor(page)
    topic(page)
    page.locator("[data-gear]").click()
    page.locator("[data-gear-tour]").click()
    seen = []
    while True:
        now = step(page)
        if now is None:
            break
        seen.append(now["key"])
        if now["key"] != "welcome":
            assert now["frame"] and now["frame"]["width"] > 10, now["key"]
        # The bubble stays in the window (once it has moved there: it glides from the last step)
        page.wait_for_function(
            """() => {
            const tour = document.querySelector('assist-router-editor-app').shadowRoot.querySelector('assist-router-editor-tour');
            const box = tour.shadowRoot.querySelector('[data-tour-bubble]').getBoundingClientRect();
            return box.bottom <= innerHeight && box.right <= innerWidth && box.top >= 0 && box.left >= 0;
        }""",
            timeout=3000,
        )
        bubble = step(page)["bubble"]
        assert bubble["x"] >= 0 and bubble["y"] >= 0
        assert bubble["x"] + bubble["width"] <= 1440 and bubble["y"] + bubble["height"] <= 900, now[
            "key"
        ]
        assert now["text"] and "_" not in now["title"], now["key"]
        next_step(page)
    assert seen == STEPS
    assert page.evaluate("localStorage.getItem('assist-router-editor-tour')") == "done"


def test_skipped_once_it_stays_away_and_comes_back_from_the_gear(page: Page) -> None:
    open_editor(page, tour=True)
    page.locator(f"{TOUR} [data-tour-skip]").click()
    expect(page.locator(TOUR)).to_have_count(0)
    assert page.evaluate("localStorage.getItem('assist-router-editor-tour')") == "done"
    # Opened again in the same browser: it remembers the tour was seen
    open_editor(page, tour=True)
    expect(page.locator(TOUR)).to_have_count(0)
    page.locator("[data-gear]").click()
    page.locator("[data-gear-tour]").click()
    expect(page.locator(f"{TOUR} [data-tour-bubble='welcome']")).to_be_visible()
    # The ⚙ window closed for the tour
    expect(page.locator("[data-gear-pop]")).to_have_count(0)


def test_the_keyboard_moves_through_it_and_escape_closes_it(page: Page) -> None:
    open_editor(page, tour=True)
    page.keyboard.press("ArrowRight")
    expect(page.locator(f"{TOUR} [data-tour-bubble='tree']")).to_be_visible()
    page.keyboard.press("ArrowLeft")
    expect(page.locator(f"{TOUR} [data-tour-bubble='welcome']")).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.locator(f"{TOUR} [data-tour-bubble='tree']")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator(TOUR)).to_have_count(0)


def test_nothing_under_it_takes_a_click_or_a_key(page: Page) -> None:
    open_editor(page, tour=True)
    next_step(page)  # the tree, framed
    # Ctrl+Z of the editor does nothing while the tour is open, a click on the tree neither
    page.mouse.click(150, 300)
    assert page.evaluate("window.editor.app._selected") is None
    expect(page.locator(TOUR)).to_have_count(1)


def test_a_step_whose_part_is_not_there_is_left_out(page: Page) -> None:
    open_editor(page)
    # No topic chosen: no Kind of topic, but the check and the file are there; fold the right column: no tester
    page.locator("[data-fold-column='right']").click()
    page.locator("[data-gear]").click()
    page.locator("[data-gear-tour]").click()
    seen = []
    while (now := step(page)) is not None:
        seen.append(now["key"])
        next_step(page)
    assert "tester" not in seen and "side" not in seen
    assert seen[:2] == ["welcome", "tree"]


def test_the_tour_speaks_english_too(page: Page) -> None:
    open_editor(page, language="en", tour=True)
    first = step(page)
    assert first["title"] == "Welcome to the editor"
    assert first["count"].lower() == f"tour · 1 of {len(STEPS)}"
