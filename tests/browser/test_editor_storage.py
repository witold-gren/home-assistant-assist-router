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
