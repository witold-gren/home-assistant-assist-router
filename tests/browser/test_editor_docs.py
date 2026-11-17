"""The "?" of the editor's top bar: the guide to the editor on the documentation site, in a new tab."""

from __future__ import annotations

from playwright.sync_api import Page

from .test_editor_app import open_editor

EDITOR = "/custom_components/assist_router/www/editor/editor-app.js"
SITE = "https://witold-gren.github.io/home-assistant-assist-router/"
POLISH = f"{SITE}pl/editor/"
ENGLISH = f"{SITE}editor/"


def test_the_guide_is_in_the_language_of_home_assistant(page: Page) -> None:
    urls = page.evaluate(
        f"async () => {{ const e = await import('{EDITOR}');"
        " return ['pl', 'pl-PL', 'en', 'de', undefined].map((language) => e.editorDocsUrl(language)); }"
    )
    assert urls == [POLISH, POLISH, ENGLISH, ENGLISH, ENGLISH]


def open_guide(page: Page, language: str) -> tuple[str, list]:
    open_editor(page, language=language)
    page.evaluate(
        "() => { window.opened = []; window.open = (...args) => { window.opened.push(args); }; }"
    )
    button = page.locator("[data-docs]")
    title = button.get_attribute("title")
    button.click()
    return title, page.evaluate("window.opened")


def test_the_question_mark_opens_the_polish_guide_in_a_new_tab(page: Page) -> None:
    title, opened = open_guide(page, "pl")
    assert title.startswith("Dokumentacja")
    assert opened == [[POLISH, "_blank", "noopener"]]


def test_the_question_mark_opens_the_english_guide_in_a_new_tab(page: Page) -> None:
    title, opened = open_guide(page, "en")
    assert title.startswith("Documentation")
    assert opened == [[ENGLISH, "_blank", "noopener"]]


def _help_of(page: Page, part: str) -> dict:
    """Open the "?" of a part: its window, never a new tab."""
    page.evaluate(
        "() => { window.opened = []; window.open = (...args) => { window.opened.push(args); }; }"
    )
    page.locator(f"[data-help='{part}']").click()
    pop = page.locator(f"[data-help-pop='{part}']")
    pop.wait_for()
    return {
        "title": pop.locator("b").inner_text(),
        "text": pop.locator("p").inner_text(),
        "more": pop.locator("[data-help-more]").get_attribute("href"),
        "opened": page.evaluate("window.opened"),
    }


def test_the_question_mark_of_a_part_opens_a_window_with_what_it_does(page: Page) -> None:
    open_editor(page, language="pl")
    for part, title, anchor in [
        ("tree", "Drzewo", "screen"),
        ("middle", "To, co wybrane", "screen"),
        ("side", "Sprawdzenie, plik i tester", "save"),
    ]:
        help_ = _help_of(page, part)
        assert help_["title"] == title
        assert len(help_["text"]) > 80
        assert help_["more"] == f"{POLISH}#{anchor}"
        assert help_["opened"] == []
        page.locator("[data-help-close]").click()
        assert page.locator("[data-help-pop]").count() == 0


def test_the_window_closes_with_escape_or_a_click_beside_it(page: Page) -> None:
    open_editor(page, language="pl")
    _help_of(page, "tree")
    page.keyboard.press("Escape")
    assert page.locator("[data-help-pop]").count() == 0
    _help_of(page, "tree")
    page.locator("[data-help-shade]").click(position={"x": 600, "y": 500})
    assert page.locator("[data-help-pop]").count() == 0


def test_the_link_of_the_middle_window_follows_what_is_chosen(page: Page) -> None:
    open_editor(page, language="en")
    for key, anchor in {
        "topics/weather": "topic",
        "people": "editor",
        "@settings": "editor",
        "@tests": "tests",
    }.items():
        page.locator(f"[data-node='{key}']").click()
        assert _help_of(page, "middle")["more"] == f"{ENGLISH}#{anchor}", key
        page.keyboard.press("Escape")


def test_the_save_and_history_dialogs_have_their_own_question_mark(page: Page) -> None:
    from .test_editor_save import change, open_editor as open_with_server, open_save

    open_with_server(page, language="pl")
    change(page, "the weather", "rain and sun")
    open_save(page)
    help_ = _help_of(page, "save")
    assert help_["title"] == "Zapis router.yaml" and len(help_["text"]) > 80
    assert help_["more"] == f"{POLISH}#save"
    assert help_["opened"] == []
    # Esc closes the window of the "?", not the dialog under it.
    page.keyboard.press("Escape")
    assert page.locator("[data-help-pop]").count() == 0
    assert page.locator("[data-save-dialog]").count() == 1
    page.keyboard.press("Escape")
    page.locator("[data-history]").click()
    help_ = _help_of(page, "history")
    assert help_["title"] == "Historia zapisów"
    assert help_["more"] == f"{POLISH}#history"


def test_a_question_home_assistant_never_answers_ends_in_a_message(page: Page) -> None:
    open_editor(page)
    result = page.evaluate(
        """async () => { const { callWS, WsTimeout } = await import('/custom_components/assist_router/www/editor/ws.js');
        const hass = { language: 'pl', callWS: () => new Promise(() => {}) };
        try { await callWS(hass, { type: 'assist_router/editor/load' }, 1000); return 'answered'; }
        catch (error) { return [error instanceof WsTimeout, error.message]; } }"""
    )
    assert result[0] is True
    assert "nie odpowiedział w ciągu 1 s (assist_router/editor/load)" in result[1]


def test_an_answer_in_time_clears_the_timer(page: Page) -> None:
    open_editor(page)
    result = page.evaluate(
        """async () => { const { callWS } = await import('/custom_components/assist_router/www/editor/ws.js');
        const cleared = []; const clear = window.clearTimeout;
        window.clearTimeout = (id) => { cleared.push(id); clear(id); };
        const answer = await callWS({ callWS: async () => 'ok' }, { type: 'x' });
        window.clearTimeout = clear; return [answer, cleared.length]; }"""
    )
    assert result == ["ok", 1]
