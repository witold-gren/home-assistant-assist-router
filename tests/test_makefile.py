"""The Makefile follows the common standard of the house (standards/gpu-studio.md, sections 2
and 8a): the same targets in the same groups, both languages, "1. Start" needing only Docker,
no aliases."""

from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
STANDARD = Path.home() / "Home Assistant" / "standards" / "gpu-studio.md"
HIDDEN = {"docker-check", "uv-check"}
# The targets of a panel of Home Assistant (section 8a).
PANEL = {
    "help",
    "demo",
    "demo-clean",
    "docs",
    "docs-serve",
    "doctor",
    "deploy",
    "setup",
    "demo-local",
    "test",
    "test-browser",
    "test-docker",
    "test-all",
    "lint",
    "format",
    "docs-build",
    "screenshots",
    "clean",
}
GROUPS = [
    ("1. Start", "1. Start"),
    ("2. Home Assistant", "2. Home Assistant"),
    ("3. Development", "3. Rozwój"),
]
START = ["help", "demo", "demo-clean", "docs", "docs-serve", "doctor"]
NO_TOOLS = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home())}


def targets() -> dict[str, list[str]]:
    """Each target with the targets it needs (order-only ones too)."""
    found = {}
    for name, needs in re.findall(r"^([a-z0-9-]+):(?!=)([^#\n]*)", MAKEFILE, re.M):
        found[name] = needs.replace("|", " ").split()
    return found


def groups() -> dict[str, str]:
    """The group of each described target."""
    group, found = None, {}
    for line in MAKEFILE.splitlines():
        if line.startswith("##@ "):
            group = line[4:].split(" | ")[0]
        elif match := re.match(r"^([a-z0-9-]+):.*## ", line):
            found[match.group(1)] = group
    return found


def needs_all(name: str, known: dict[str, list[str]]) -> set[str]:
    seen, todo = set(), [name]
    while todo:
        for need in known.get(todo.pop(), []):
            if need in known and need not in seen:
                seen.add(need)
                todo.append(need)
    return seen


def standard_row() -> str:
    if not STANDARD.exists():
        pytest.skip("the standard of the house is not on this computer")
    repository = f"`{ROOT.name}`"
    return next(line for line in STANDARD.read_text("utf-8").splitlines() if repository in line)


def test_every_target_is_described_in_both_languages() -> None:
    phony = re.search(r"^\.PHONY: (.+?)(?<!\\)$", MAKEFILE, re.M | re.S)
    listed = set(phony.group(1).replace("\\\n", " ").split())
    described = dict(re.findall(r"^([a-z0-9-]+):.*?## (.+)$", MAKEFILE, re.M))
    assert listed - HIDDEN == set(described)
    for target, text in described.items():
        english, _, polish = text.partition(" | ")
        assert english and polish, target


def test_the_helpers_are_not_in_the_list() -> None:
    for helper in HIDDEN:
        assert re.search(rf"^{helper}:\s*$", MAKEFILE, re.M), helper


def test_the_targets_of_a_panel_are_there() -> None:
    assert set(targets()) >= PANEL


def test_the_groups_come_in_the_order_of_the_standard() -> None:
    headings = re.findall(r"^##@ (.+)$", MAKEFILE, re.M)
    assert headings == [f"{english} | {polish}" for english, polish in GROUPS]
    found = groups()
    assert [name for name, group in found.items() if group == "1. Start"] == START
    assert [name for name, group in found.items() if group == "2. Home Assistant"] == ["deploy"]


def test_start_needs_only_docker() -> None:
    known = targets()
    for name in [*START, "deploy"]:
        assert not {"setup", "setup-dev", "uv-check"} & needs_all(name, known), name
        assert ".venv" not in MAKEFILE.split(f"\n{name}:", 1)[1].split("\n\n", 1)[0], name


def test_there_are_no_aliases() -> None:
    known = targets()
    assert "ui" not in known
    aliases = [
        name
        for name in known
        if re.search(rf"^{name}:[^\n]*\n(?!\t)", MAKEFILE + "\n", re.M)
        and name not in {"setup", "setup-dev", "test-all"}
        and not name.startswith((".", "$"))
    ]
    assert aliases == []


def test_the_developer_python_comes_from_uv() -> None:
    assert re.search(r"^PYTHON_VERSION \?= 3\.14$", MAKEFILE, re.M)
    assert "uv venv -q --python $(PYTHON_VERSION)" in MAKEFILE
    assert "brew install" not in MAKEFILE and "-m venv" not in MAKEFILE


def test_plain_tests_never_build_images() -> None:
    known = targets()
    test = MAKEFILE.split("\ntest:", 1)[1].split("\n\n", 1)[0]
    docker = MAKEFILE.split("\ntest-docker:", 1)[1].split("\n\n", 1)[0]
    assert '-m "not docker"' in test and "-m docker" in docker
    assert "docker-check" in known["test-docker"]
    assert known["test-all"] == ["lint", "test", "test-browser", "test-docker"]
    assert '"docker:' in (ROOT / "pyproject.toml").read_text("utf-8")


def test_the_documentation_is_built_in_docker() -> None:
    build = MAKEFILE.split("\ndocs-build:", 1)[1].split("\n\n", 1)[0]
    assert "docker build" in build and "--target docs-site" in build and "dest=site" in build
    # The folder Docker writes is for its owner only: the web server of docs-hub could not read it.
    assert "chmod -R u+rwX,go+rX site" in build
    serve = MAKEFILE.split("\ndocs-serve:", 1)[1].split("\n\n", 1)[0]
    assert "--target docs-tools" in serve and "127.0.0.1:$(DOCS_PORT):$(DOCS_PORT)" in serve
    assert ".venv-docs/bin" not in MAKEFILE


def test_the_ports_are_the_ones_of_the_standard() -> None:
    row = [cell.strip() for cell in standard_row().split("|")]
    demo, docs = row[4], row[5]
    port = re.search(r"^(?:DEMO_PORT|UI_PORT) \?= (\d+)$", MAKEFILE, re.M).group(1)
    assert port == demo
    assert re.search(rf"^DOCS_PORT \?= {docs}$", MAKEFILE, re.M)


@pytest.mark.skipif(not shutil.which("make"), reason="make not installed")
@pytest.mark.parametrize(("lang", "index"), [("en", 0), ("pl", 1)])
def test_make_help_shows_the_groups(lang: str, index: int) -> None:
    result = subprocess.run(
        ["make", "-s", "help", f"HELP_LANG={lang}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    shown = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    places = [shown.index(group[index]) for group in GROUPS]
    assert places == sorted(places)
    assert "  demo " in shown and "  ui " not in shown and "docker-check" not in shown


@pytest.mark.skipif(not shutil.which("make"), reason="make not installed")
@pytest.mark.parametrize("target", ["demo", "docs-build", "docs-serve"])
def test_without_docker_a_clear_message(target: str) -> None:
    result = subprocess.run(
        ["make", "-s", target], cwd=ROOT, capture_output=True, text=True, env=NO_TOOLS, check=False
    )
    assert result.returncode != 0
    assert "Docker Desktop" in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which("make"), reason="make not installed")
def test_without_uv_a_clear_message() -> None:
    result = subprocess.run(
        ["make", "-s", "uv-check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=NO_TOOLS,
        check=False,
    )
    assert result.returncode != 0
    assert "astral.sh/uv" in result.stdout + result.stderr


@pytest.mark.skipif(not shutil.which("make"), reason="make not installed")
def test_doctor_installs_nothing_and_needs_no_setup() -> None:
    assert targets()["doctor"] == []
    result = subprocess.run(
        ["make", "-s", "doctor"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=NO_TOOLS,
        check=False,
    )
    assert "MISSING  Docker Desktop" in result.stdout
    assert "MISSING  uv" in result.stdout
