"""The ⚙ of the editor's top bar: a small window under it with the look and the language of the editor.

Home Assistant decides both ("As in HA"); one chosen here wins and is kept by the browser.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

from .test_editor_app import open_editor

EDITOR = "/custom_components/assist_router/www/editor/editor-app.js"
POP = "[data-gear-pop]"


def open_gear(page: Page, **options) -> None:
    open_editor(page, **options)
    page.locator("[data-gear]").click()
    expect(page.locator(POP)).to_be_visible()


def test_the_window_opens_under_the_cog_and_leaves_the_address(page: Page) -> None:
    open_editor(page, language="en")
    address = page.evaluate("location.href")
    gear = page.locator("[data-gear]")
    expect(gear).to_have_attribute("aria-expanded", "false")
    gear.click()
    expect(gear).to_have_attribute("aria-expanded", "true")
    button, pop = gear.bounding_box(), page.locator(POP).bounding_box()
    assert pop["y"] >= button["y"] + button["height"]
    assert abs((pop["x"] + pop["width"]) - (button["x"] + button["width"])) < 2
    assert page.evaluate("location.href") == address
    expect(page.locator(f"{POP} b")).to_have_text("Look and language")
    # The labels of the segments stay on one line.
    heights = page.locator(f"{POP} .segment button").evaluate_all(
        "(buttons) => buttons.map((b) => b.getBoundingClientRect().height)"
    )
    assert max(heights) - min(heights) < 1


def test_the_look_is_chosen_in_the_window_and_the_window_stays(page: Page) -> None:
    open_gear(page)
    app = page.locator("assist-router-editor-app")
    page.locator(f"{POP} [data-segment='theme'] [data-value='dark']").click()
    expect(app).to_have_attribute("data-theme", "dark")
    expect(page.locator("[data-theme-button]")).to_have_attribute("data-theme-button", "dark")
    expect(page.locator(f"{POP} [data-segment='theme'] [data-value='dark']")).to_have_attribute(
        "aria-pressed", "true"
    )
    assert page.evaluate("() => localStorage.getItem('assist-router-editor-theme')") == "dark"
    expect(page.locator(POP)).to_be_visible()
    # The button in the bar is still there (a click on it is outside, so the window closes) and the window follows it.
    page.locator("[data-theme-button]").click()  # dark → as Home Assistant
    expect(page.locator(POP)).to_have_count(0)
    page.locator("[data-gear]").click()
    expect(page.locator(f"{POP} [data-segment='theme'] [data-value='auto']")).to_have_attribute(
        "aria-pressed", "true"
    )


def test_the_language_follows_home_assistant_until_one_is_chosen(page: Page) -> None:
    open_gear(page, language="en")
    title = page.locator("[data-docs]")
    expect(title).to_have_attribute("title", "Documentation: the guide to the editor (new tab)")
    page.locator(f"{POP} [data-segment='language'] [data-value='pl']").click()
    expect(page.locator(f"{POP} b")).to_have_text("Wygląd i język")
    expect(title).to_have_attribute("title", "Dokumentacja: przewodnik po edytorze (nowa karta)")
    assert page.evaluate("() => localStorage.getItem('assist-router-editor-language')") == "pl"
    # What the editor hands on (the forms, the tester, the dialogs) speaks the chosen language too.
    assert page.evaluate("() => window.editor.app.hass.language") == "pl"
    # A new hass from Home Assistant keeps the choice.
    page.evaluate(
        "() => { window.editor.app.hass = { ...window.editor.app._haHass, states: {} }; }"
    )
    assert page.evaluate("() => window.editor.app.hass.language") == "pl"
    page.locator(f"{POP} [data-segment='language'] [data-value='auto']").click()
    expect(page.locator(f"{POP} b")).to_have_text("Look and language")
    assert page.evaluate("() => window.editor.app.hass === window.editor.app._haHass")


def test_a_chosen_language_is_kept_by_the_browser(page: Page) -> None:
    page.evaluate("() => localStorage.setItem('assist-router-editor-language', 'en')")
    open_editor(page, language="pl")
    expect(page.locator("[data-docs]")).to_have_attribute(
        "title", "Documentation: the guide to the editor (new tab)"
    )


def test_escape_a_click_outside_and_the_cog_close_the_window(page: Page) -> None:
    open_gear(page)
    page.keyboard.press("Escape")
    expect(page.locator(POP)).to_have_count(0)
    page.locator("[data-gear]").click()
    page.locator("[data-path]").click()
    expect(page.locator(POP)).to_have_count(0)
    page.locator("[data-gear]").click()
    page.locator("[data-gear]").click()
    expect(page.locator(POP)).to_have_count(0)
    page.locator("[data-gear]").click()
    page.locator("[data-ha-menu]").click()
    expect(page.locator(POP)).to_have_count(0)


def test_the_hass_with_a_language(page: Page) -> None:
    result = page.evaluate(f"""async () => {{
        const {{ withLanguage }} = await import('{EDITOR}');
        const hass = {{ language: 'en', states: {{}} }};
        return [withLanguage(hass, 'auto') === hass, withLanguage(hass, 'en') === hass, withLanguage(hass, 'xx') === hass,
                withLanguage(hass, 'pl').language, withLanguage(hass, 'pl').states === hass.states, hass.language,
                withLanguage(undefined, 'pl')];
    }}""")
    assert result == [True, True, True, "pl", True, "en", None]
