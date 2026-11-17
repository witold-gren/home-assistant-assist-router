"""The editor never hangs (standard section 9a): on a big router.yaml, going through the topics, the settings and the
whole file leaves no task of the page longer than 500 ms, and the measure does see a page that blocks."""

from __future__ import annotations

from playwright.sync_api import Page

LONGEST_MS = 500
TOPICS = 150
EXAMPLES = 25


def big_file() -> str:
    lines = ["# A big router of a made-up home", "", "household: Tom and Ann", "people:"]
    lines += [f"  person_{n}:\n    name: Person {n}" for n in range(30)]
    lines.append("topics:")
    for n in range(TOPICS):
        lines.append(f"  # Topic number {n}")
        lines.append(f"  topic_{n}:")
        lines.append(f"    description: what topic {n} is about, said in a few words")
        lines.append(f"    entities: [sensor.thing_{n}, light.lamp_{n}]")
        lines.append("    examples:")
        lines += [f"      - Question {k} about topic {n}?" for k in range(EXAMPLES)]
        lines.append("")
    return "\n".join(lines) + "\n"


WATCH = """() => { window.longTasks = [];
    new PerformanceObserver((list) => { for (const entry of list.getEntries()) window.longTasks.push(entry.duration); })
        .observe({ type: "longtask", buffered: true }); }"""


def test_going_through_a_big_router_file_never_blocks_the_page(page: Page) -> None:
    page.evaluate(WATCH)
    page.evaluate("(options) => window.editor.open(options)", {"file": big_file()})
    page.wait_for_selector("[data-node='topics/topic_0']")
    page.evaluate("window.longTasks = []")
    for n in (0, 37, 74, 111, 149):
        page.locator(f"[data-node='topics/topic_{n}']").click()
    for key in ("people", "@settings", "@unrecognized", "@tests"):
        page.locator(f"[data-node='{key}']").click()
    page.locator("[data-node='topics/topic_74']").click()
    for tab in ("node", "file", "form"):
        page.locator(f"[data-tab='{tab}']").click()
    page.locator("[data-fold-all]").click()
    page.locator("[data-unfold-all]").click()
    page.locator("[data-search]").fill("topic_12")
    page.locator("[data-search]").fill("")
    page.wait_for_timeout(500)
    tasks = page.evaluate("window.longTasks")
    assert max(tasks, default=0) < LONGEST_MS, sorted(tasks)[-5:]


def test_the_measure_sees_a_page_that_blocks(page: Page) -> None:
    page.evaluate(WATCH)
    page.evaluate(
        "() => setTimeout(() => { const end = performance.now() + 700; while (performance.now() < end); })"
    )
    page.wait_for_timeout(900)
    assert max(page.evaluate("window.longTasks"), default=0) >= LONGEST_MS


SLOW_SERVER = """(kind) => { const app = window.editor.app; const real = app.hass.callWS.bind(app.hass);
    window.inFlight = 0; window.mostInFlight = 0; window.saves = [];
    app.hass = { ...app.hass, callWS: async (message) => {
        if (message.type !== kind) return real(message);
        window.inFlight++; window.mostInFlight = Math.max(window.mostInFlight, window.inFlight);
        await new Promise((resolve) => setTimeout(resolve, 1500));
        try { return await real(message); } finally { window.inFlight--; window.saves.push(message); } } }; }"""


def test_a_slow_home_assistant_gets_one_save_of_the_draft_at_a_time(page: Page) -> None:
    from .test_editor_app import open_editor

    open_editor(page)
    page.wait_for_selector("[data-node]")
    page.evaluate(SLOW_SERVER, "assist_router/editor/save_draft")
    for word in ("rain", "sun", "wind", "snow"):
        page.evaluate(
            "(word) => window.editor.app._setText(window.editor.app._text.replace(/description: [^\\n]*weather[^\\n]*/, "
            "`description: the weather and ${word}`))",
            word,
        )
        page.wait_for_timeout(900)
    page.wait_for_function("window.inFlight === 0 && window.saves.length > 0", timeout=15000)
    page.wait_for_timeout(2500)
    assert page.evaluate("window.mostInFlight") == 1
    saves = page.evaluate("window.saves")
    assert "the weather and snow" in saves[-1]["text"]
    assert len(saves) < 4
