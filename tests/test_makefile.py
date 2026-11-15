"""`make help` lists every target with a description in English and Polish."""

from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")


def test_every_target_is_described_in_both_languages():
    phony = re.search(r"^\.PHONY: (.+?)(?<!\\)$", MAKEFILE, re.M | re.S)
    targets = set(phony.group(1).replace("\\\n", " ").split())
    described = dict(re.findall(r"^([a-z0-9-]+):.*?## (.+)$", MAKEFILE, re.M))
    assert targets == set(described)
    for target, text in described.items():
        english, _, polish = text.partition(" | ")
        assert english and polish, target


@pytest.mark.skipif(not shutil.which("make"), reason="make not installed")
@pytest.mark.parametrize(("lang", "expected"), [("en", "1. Setup"), ("pl", "1. Instalacja")])
def test_make_help(lang, expected):
    result = subprocess.run(
        ["make", "-s", "help", f"HELP_LANG={lang}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert expected in result.stdout
    assert "  ui " in re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
