"""The chosen node in the address (#/...): a link or a reload opens the editor on it, once router.yaml and the files
of sentences have loaded, and choosing another node changes the address without a new step of history (address.js)."""

from __future__ import annotations

from playwright.sync_api import Page

from .test_editor_app import open_editor


def address(page: Page) -> str:
    return page.evaluate("window.location.hash")


def chosen(page: Page) -> list[str]:
    return page.locator(".node.sel").evaluate_all(
        "(nodes) => nodes.map((node) => node.dataset.node)"
    )


def open_at(page: Page, hash_: str) -> None:
    page.evaluate(
        "(hash) => history.replaceState(history.state, '', location.pathname + location.search + hash)",
        hash_,
    )
    open_editor(page)
    page.wait_for_selector("[data-node]")


def test_choosing_a_node_puts_it_in_the_address(page: Page) -> None:
    open_editor(page)
    page.evaluate("""() => { window.pushed = 0; const push = history.pushState.bind(history);
        history.pushState = (...args) => { window.pushed++; push(...args); }; }""")
    page.locator("[data-node='topics/weather']").click()
    assert address(page) == "#/topics/weather"
    assert page.evaluate("window.pushed") == 0


def test_the_editor_opens_on_the_node_in_the_address(page: Page) -> None:
    open_at(page, "#/topics/lights")
    page.wait_for_selector(".node.sel")
    assert chosen(page) == ["topics/lights"]
    assert address(page) == "#/topics/lights"


def test_a_special_node_is_named_in_the_address_too(page: Page) -> None:
    open_at(page, "#/@settings")
    page.wait_for_selector(".node.sel")
    assert chosen(page) == ["@settings"]


def test_a_node_that_is_gone_opens_nothing_and_leaves_the_address(page: Page) -> None:
    open_at(page, "#/topics/gone")
    page.wait_for_function("window.location.hash === ''")
    assert chosen(page) == []
