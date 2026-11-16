"""The "?" of the editor's top bar: the guide to the editor on the documentation site, in a new tab."""

from __future__ import annotations

from playwright.sync_api import Page

from .test_editor_app import open_editor

EDITOR = "/custom_components/assist_router/www/editor/editor-app.js"
SITE = "https://witold-gren.github.io/home-assistant-assist-router/"
POLISH = f"{SITE}pl/przewodnik-edytora.html"
ENGLISH = f"{SITE}en/editor-guide.html"


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
