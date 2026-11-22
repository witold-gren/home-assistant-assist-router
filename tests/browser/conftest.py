"""Run the editor of router.yaml in Google Chrome against a server kept in memory."""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

from playwright.sync_api import Page, sync_playwright
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCREEN = {"width": 1440, "height": 900}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """The browser tests run without Home Assistant (-p no:homeassistant)."""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="session")
def browser():
    if not shutil.which("google-chrome") and not Path("/Applications/Google Chrome.app").exists():
        pytest.skip("Google Chrome not installed")
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(channel="chrome", headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser, base_url: str) -> Iterator[Page]:
    page = browser.new_page(viewport=SCREEN)
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    # Questions are windows of the editor (ask.js); a dialog of the browser is a mistake.
    page.on(
        "dialog",
        lambda dialog: (page.errors.append(f"browser dialog: {dialog.message}"), dialog.dismiss()),
    )
    page.goto(f"{base_url}/tests/js/editor-harness.html")
    page.wait_for_function("window.editorReady === true")
    yield page
    assert page.errors == []
    page.close()
