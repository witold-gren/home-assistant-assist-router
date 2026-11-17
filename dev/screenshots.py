"""Pictures of the editor for the documentation site (docs/editor.md, docs/editor.pl.md).

They are taken on the demo (dev/editor-demo.html) with its made-up home, so no real home is in them.
Every step is a real click in the editor, so the names in the guide are the names on the screen.

    make screenshots        # both languages, into docs/assets/screens/{pl,en}/
"""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "assets" / "screens"
SCREEN = {"width": 1440, "height": 900}

# The example of the guide in each language: a sentence of the log that no topic answers, the topic
# made of it, its words, more examples, the pattern of its entities, and an HA command to try.
STORY = {
    "pl": {
        "log_index": 1,
        "sentence": "Kiedy przyjedzie śmieciarka?",
        "topic": "smieci",
        "description": "śmieci, śmieciarka, wywóz śmieci, odbiór odpadów, kosz, bio, plastik",
        "examples": ["Kiedy wywóz śmieci?", "Kiedy trzeba wystawić kosz?"],
        "pattern": "sensor.wywoz_smieci*",
        "file": "lampy.yaml",
        "intent_sentence": "zaświeć {name}",
        "response": "Już świeci.",
        "try": "zaświeć salon",
    },
    "en": {
        "log_index": 1,
        "sentence": "When do the bins go out?",
        "topic": "bins",
        "description": "bins, bin lorry, rubbish collection, recycling, plastic, garden waste",
        "examples": ["When is the bin collection?", "Which bin goes out this week?"],
        "pattern": "sensor.bin_collection*",
        "file": "lamps.yaml",
        "intent_sentence": "light up {name}",
        "response": "It is on.",
        "try": "light up the living room",
    },
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def open_demo(page: Page, base: str, language: str) -> None:
    page.goto(f"{base}/dev/editor-demo.html" + ("?lang=en" if language == "en" else ""))
    page.wait_for_selector("[data-tree]")
    page.wait_for_timeout(1500)


def shot(page: Page, language: str, name: str) -> None:
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / language / f"{name}.png"))
    print(f"  {language}/{name}.png")


def add_to_list(page: Page, path: str, value: str) -> None:
    field = page.locator(f"[data-list='{path}'] input").last
    field.fill(value)
    field.press("Enter")
    page.wait_for_timeout(700)


def take(page: Page, base: str, language: str) -> None:
    story = STORY[language]
    topic = story["topic"]
    (OUT / language).mkdir(parents=True, exist_ok=True)
    open_demo(page, base, language)

    # 1. The screen: a topic of the example file in its form.
    first = page.locator("[data-node^='topics/']").first
    first.click()
    shot(page, language, "01-screen")

    # 2. Learning: the sentences nobody answered.
    page.locator("[data-node='@unrecognized']").click()
    shot(page, language, "02-unrecognized")

    # 3. A new topic made of one of them, named and described.
    page.locator("[data-new-topic]").nth(story["log_index"]).click()
    page.wait_for_timeout(600)
    key = page.locator("[data-field='@key'] input")
    key.fill(topic)
    key.press("Tab")
    page.wait_for_timeout(600)
    description = page.locator(f"[data-field='topics/{topic}/description'] textarea")
    description.fill(story["description"])
    description.press("Tab")
    for example in story["examples"]:
        add_to_list(page, f"topics/{topic}/examples", example)
    page.locator("[data-field='@key']").scroll_into_view_if_needed()
    page.evaluate("() => window.scrollTo(0, 0)")
    page.locator("[data-field='@key']").evaluate(
        "(el) => el.closest('main, .main, section')?.scrollTo?.(0, 0)"
    )
    shot(page, language, "03-new-topic")

    # 4. Its data: the entities counted at once, and what the model gets.
    add_to_list(page, f"topics/{topic}/entities", story["pattern"])
    add_to_list(page, f"topics/{topic}/details", story["pattern"])
    page.locator("[data-sources]").scroll_into_view_if_needed()
    preview = page.locator("[data-sources] summary").first
    preview.click()
    page.wait_for_timeout(400)
    page.locator("[data-sources]").evaluate("(el) => el.scrollIntoView({ block: 'start' })")
    shot(page, language, "04-data")

    # 5. The tester: the way of the sentence on the draft.
    page.locator("[data-sentence]").fill(story["sentence"])
    page.locator("[data-run]").click()
    page.wait_for_selector("[data-step='answer']")
    page.locator("[data-step='router']").scroll_into_view_if_needed()
    shot(page, language, "05-tester")

    # 6. The sentence goes to the test set.
    page.locator("[data-add-test]").click()
    page.wait_for_timeout(500)
    page.locator("[data-node='@tests']").click()
    shot(page, language, "06-tests")

    # 7. Saving: changes, differences, what to look at, the tests on the draft.
    page.locator("[data-save]").first.click()
    page.wait_for_selector("[data-save-dialog]")
    page.locator("[data-save-dialog] [data-run-tests]").click()
    page.wait_for_timeout(1200)
    shot(page, language, "07-save")
    page.locator("[data-save-dialog] [data-confirm]").click()
    page.wait_for_timeout(1000)

    # 8. History of saves.
    page.locator("[data-history]").click()
    page.wait_for_selector("[data-history-dialog]")
    page.locator("[data-history-dialog] [data-version]").first.click()
    shot(page, language, "08-history")
    page.locator("[data-history-dialog] [data-close]").click()
    page.wait_for_timeout(300)

    # 9. A command of HA: a new file, an intent, a sentence, an answer, and what HA recognizes.
    page.once("dialog", lambda dialog: dialog.accept(story["file"]))
    page.locator("[data-add-sentences]").click()
    page.wait_for_timeout(800)
    intent = page.locator("[data-new-intent]")
    intent.fill("HassTurnOn")
    intent.press("Enter")
    page.wait_for_timeout(600)
    if not page.locator("[data-intent='HassTurnOn']").count():
        intent.locator("xpath=following-sibling::button[1]").click()
        page.wait_for_timeout(600)
    field = page.locator("[data-add-sentence]").first
    field.fill(story["intent_sentence"])
    field.press("Enter")
    page.wait_for_timeout(400)
    response = page.locator("[data-response]").first
    response.fill(story["response"])
    response.press("Tab")
    page.locator("[data-sentences-save]").click()
    page.wait_for_timeout(1200)
    page.locator("[data-sentences-sample]").fill(story["try"])
    page.locator("[data-sentences-run]").click()
    page.wait_for_timeout(1200)
    shot(page, language, "09-command")


def main(languages: list[str]) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome")
        for language in languages:
            page = browser.new_page(
                viewport=SCREEN, locale="pl-PL" if language == "pl" else "en-GB"
            )
            page.on("pageerror", lambda error: print("page error:", error))
            take(page, base, language)
            page.close()
        browser.close()
    server.shutdown()


if __name__ == "__main__":
    main(sys.argv[1:] or ["pl", "en"])
