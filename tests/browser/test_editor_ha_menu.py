"""The menu of Home Assistant in the editor: hidden when it opens, its menu button shows and hides it, and it comes
back on any other page; always by the kiosk mode, never by the user's own place of the menu (ha-menu.js)."""

from __future__ import annotations

from playwright.sync_api import Page

from .test_editor_app import open_editor

FAKE_APP = """([dock, kiosk, phone]) => {
    const app = document.createElement("home-assistant");
    // A Home Assistant with the kiosk mode has it in hass (false); an older one has no such key
    app.hass = kiosk ? { dockedSidebar: dock, kioskMode: false } : { dockedSidebar: dock };
    app.updates = [];
    app._updateHass = (change) => { app.updates.push(change); app.hass = { ...app.hass, ...change }; };
    if (phone) {
        const main = document.createElement("home-assistant-main");
        main.narrow = true;
        app.attachShadow({ mode: "open" }).appendChild(main);
    }
    document.body.appendChild(app);
    // The harness empties the page when it opens: the editor is put back, as Home Assistant puts in a panel.
    const editor = window.editor.app;
    const parent = editor.parentNode;
    editor.remove();
    parent.appendChild(editor);
}"""
HASS = "document.querySelector('home-assistant').hass"


def open_in_home_assistant(
    page: Page, dock: str = "docked", kiosk: bool = True, phone: bool = False
) -> None:
    open_editor(page)
    page.evaluate(FAKE_APP, [dock, kiosk, phone])


def go(page: Page, path: str) -> None:
    page.evaluate(
        """(path) => { history.pushState(null, '', path);
        window.dispatchEvent(new CustomEvent('location-changed', { detail: { replace: false } })); }""",
        path,
    )


def test_the_editor_opens_with_the_menu_of_home_assistant_hidden(page: Page) -> None:
    open_in_home_assistant(page)
    assert page.evaluate(f"{HASS}.kioskMode") is True
    changes = page.evaluate("document.querySelector('home-assistant').updates")
    assert not any("dockedSidebar" in change for change in changes)


def test_the_menu_button_shows_the_menu_and_hides_it_again(page: Page) -> None:
    open_in_home_assistant(page)
    page.locator("[data-ha-menu]").click()
    assert page.evaluate(f"{HASS}.kioskMode") is False
    page.locator("[data-ha-menu]").click()
    assert page.evaluate(f"{HASS}.kioskMode") is True
    assert page.evaluate("() => window.editor.events") == []


def test_the_menu_comes_back_on_another_page_and_when_the_editor_closes(page: Page) -> None:
    open_in_home_assistant(page)
    editor = page.evaluate("location.pathname")
    go(page, "/config/dashboard")
    assert page.evaluate(f"{HASS}.kioskMode") is False
    go(page, editor)
    assert page.evaluate(f"{HASS}.kioskMode") is True
    page.evaluate("window.editor.app.remove()")
    assert page.evaluate(f"{HASS}.kioskMode") is False


def test_on_a_phone_the_menu_button_opens_the_drawer_of_home_assistant(page: Page) -> None:
    open_in_home_assistant(page, phone=True)
    page.locator("[data-ha-menu]").click()
    assert page.evaluate(f"{HASS}.kioskMode") is False
    assert page.evaluate("() => window.editor.events") == ["hass-toggle-menu"]


def test_an_older_home_assistant_gets_its_place_of_the_menu_back(page: Page) -> None:
    open_in_home_assistant(page, kiosk=False)
    assert page.evaluate(f"{HASS}.dockedSidebar") == "always_hidden"
    page.evaluate("window.editor.app.remove()")
    assert page.evaluate(f"{HASS}.dockedSidebar") == "docked"
