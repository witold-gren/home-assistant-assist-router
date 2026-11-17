"""Folding the left and the right column (standard section 5): a button at the top of each, Ctrl/⌘+B and
Ctrl/⌘+Alt+B, a narrow rail with the button to unfold, the middle wider, the choice kept after a reload."""

from __future__ import annotations

from playwright.sync_api import Page

from .test_editor_app import FILE, open_editor

FOLDED_KEY = "assist-router-editor-folded"


def middle_width(page: Page) -> float:
    return page.locator("main.middle").bounding_box()["width"]


def fresh(page: Page) -> None:
    page.evaluate(f"localStorage.removeItem('{FOLDED_KEY}')")
    open_editor(page)
    page.wait_for_selector("[data-tree]")


def test_the_buttons_fold_and_unfold_both_columns(page: Page) -> None:
    fresh(page)
    wide = middle_width(page)
    left_before = page.locator("[data-tree]").bounding_box()["width"]
    page.locator("[data-fold-column='left']").click()
    assert page.locator("[data-tree]").count() == 0
    rail = page.locator("[data-rail='left']")
    assert rail.is_visible() and rail.bounding_box()["width"] < 40
    assert "Ctrl/⌘+B" in page.locator("[data-unfold-column='left']").get_attribute("title")
    page.locator("[data-fold-column='right']").click()
    assert page.locator("[data-rail='right']").is_visible()
    assert middle_width(page) > wide + 300
    page.locator("[data-unfold-column='left']").click()
    page.locator("[data-unfold-column='right']").click()
    assert abs(page.locator("[data-tree]").bounding_box()["width"] - left_before) < 2
    assert abs(middle_width(page) - wide) < 2


def test_the_keys_fold_the_columns_also_while_typing(page: Page) -> None:
    fresh(page)
    page.locator("[data-search]").focus()
    page.keyboard.press("Control+KeyB")
    assert page.locator("[data-rail='left']").is_visible()
    page.keyboard.press("Control+Alt+KeyB")
    assert page.locator("[data-rail='right']").is_visible()
    page.keyboard.press("Meta+KeyB")
    assert page.locator("[data-tree]").is_visible()


def test_the_folded_columns_stay_after_a_reload(page: Page) -> None:
    fresh(page)
    page.locator("[data-fold-column='right']").click()
    page.reload()
    page.evaluate("(options) => window.editor.open(options)", {"file": FILE})
    page.wait_for_selector("[data-rail='right']")
    assert page.locator("[data-side]").count() == 0
    assert (
        page.locator("[data-splitter='right']").evaluate(
            "(bar) => getComputedStyle(bar).pointerEvents"
        )
        == "none"
    )
    page.evaluate(f"localStorage.removeItem('{FOLDED_KEY}')")


def test_a_narrow_window_starts_with_the_right_column_folded(page: Page) -> None:
    page.set_viewport_size({"width": 800, "height": 900})
    fresh(page)
    assert page.locator("[data-rail='right']").is_visible()
    assert page.locator("[data-tree]").is_visible()
