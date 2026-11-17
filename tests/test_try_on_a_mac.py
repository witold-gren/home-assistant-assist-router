"""The "Try it on a Mac" section of the common standard (§8b): in both READMEs and on the
installation page in both languages, with `make demo`, the address on the demo port of the
Makefile, no login."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).parent.parent
STANDARD = Path.home() / "Home Assistant" / "standards" / "gpu-studio.md"
HEADINGS = {
    "README.md": "## Try it on a Mac",
    "README.pl.md": "## Wypróbuj na Macu",
    "docs/installation.md": "## Try it on a Mac {#try-on-a-mac}",
    "docs/installation.pl.md": "## Wypróbuj na Macu {#try-on-a-mac}",
}


def demo_port() -> str:
    makefile = (ROOT / "Makefile").read_text("utf-8")
    return re.search(r"^UI_PORT \?= (\d+)$", makefile, re.MULTILINE).group(1)


def section(name: str) -> str:
    text = (ROOT / name).read_text("utf-8")
    start = text.index(HEADINGS[name])
    end = text.find("\n## ", start + 3)
    return text[start:end]


@pytest.mark.parametrize("name", HEADINGS)
def test_each_page_says_how_to_try_it_on_a_mac(name: str) -> None:
    part = section(name)
    assert "make demo" in part
    assert f"http://127.0.0.1:{demo_port()}/dev/editor-demo.html" in part
    assert "login" in part or "logowania" in part
    assert "Docker Desktop" in part and "make demo-clean" in part
    targets = ("make test`", "make test-browser", "make docs", "make setup")
    assert all(target in part for target in targets)
    assert len(part.strip().splitlines()) <= 15


@pytest.mark.parametrize("name", HEADINGS)
def test_the_section_is_the_first_chapter(name: str) -> None:
    text = (ROOT / name).read_text("utf-8")
    assert text.index(HEADINGS[name]) == text.index("\n## ") + 1


def test_the_help_of_make_demo_gives_the_same_port() -> None:
    makefile = (ROOT / "Makefile").read_text("utf-8")
    demo = next(line for line in makefile.splitlines() if line.startswith("demo:"))
    assert set(re.findall(r"127\.0\.0\.1:(\d+)", demo)) == {demo_port()}


def test_the_demo_port_is_the_one_of_the_standard() -> None:
    if not STANDARD.exists():
        pytest.skip("the standard of the house is not on this computer")
    lines = STANDARD.read_text("utf-8").splitlines()
    row = next(line for line in lines if "`home-assistant-assist-router`" in line)
    assert f"| {demo_port()} |" in row


def test_no_page_tells_the_old_make_ui() -> None:
    for name in ("README.md", "README.pl.md"):
        assert "make ui " not in (ROOT / name).read_text("utf-8")


def test_make_demo_builds_and_runs_the_image_on_the_demo_port() -> None:
    makefile = (ROOT / "Makefile").read_text("utf-8")
    demo = makefile.split("\ndemo:", 1)[1].split("\n\n", 1)[0]
    assert "docker build -f $(DOCKERFILE) --target demo" in demo
    assert "\nDOCKERFILE := dev/docker/Dockerfile\n" in makefile
    assert "docker run --rm --init" in demo and "127.0.0.1:$(UI_PORT):$(UI_PORT)" in demo
    assert "\ndemo-clean:" in makefile and "\ndemo-local:" in makefile
    assert f"EXPOSE {demo_port()}" in (ROOT / "dev/docker/Dockerfile").read_text("utf-8")
