"""The editor without the browser's own storage (a private window, blocked site data): it opens and works, its small
choices are simply not remembered (stored.js)."""

from __future__ import annotations

from playwright.sync_api import Page

from .test_editor_app import open_editor

BLOCK = """() => Object.defineProperty(window, 'localStorage', { configurable: true,
    get() { throw new DOMException('blocked', 'SecurityError'); } })"""


def test_the_editor_works_without_the_storage_of_the_browser(page: Page) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.evaluate(BLOCK)
    open_editor(page)
    page.locator("[data-theme-button]").click()
    page.locator("[data-fold-all]").click()
    page.locator("[data-unfold-all]").click()
    page.locator("[data-node='topics/weather']").click()
    assert page.locator(".node.sel").count() == 1
    assert errors == []


def test_without_the_storage_the_tour_does_not_come_on_every_open(page: Page) -> None:
    """tourSeen() cannot read whether it was skipped: it counts as seen, ⚙ still opens it."""
    page.evaluate(
        """() => Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('blocked', 'SecurityError'); } })"""
    )
    page.evaluate(
        "(options) => window.editor.open(options)", {"file": "topics: {}\n", "tour": True}
    )
    assert page.locator("assist-router-editor-tour").count() == 0
    page.locator("[data-gear]").click()
    page.locator("[data-gear-tour]").click()
    assert page.locator("assist-router-editor-tour [data-tour-bubble='welcome']").is_visible()
