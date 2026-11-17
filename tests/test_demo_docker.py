"""`make demo` in Docker (§8b of the common standard): the image builds, the editor's demo page
and everything it loads answer, and nothing is left behind once it stops. Skipped without a
running Docker."""

from __future__ import annotations

from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.request
import uuid

import pytest

ROOT = Path(__file__).parent.parent
IMAGE = "assist-router-demo-test"
PAGES = [
    "dev/editor-demo.html",
    "dev/demo-home.js",
    "tests/js/mock-editor.js",
    "custom_components/assist_router/www/editor/editor-app.js",
    "custom_components/assist_router/www/vendor/yaml.js",
    "router.example.yaml",
    "router.example.pl.yaml",
]


def docker_runs() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not docker_runs(), reason="Docker is not running here"),
]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def status(url: str, seconds: int = 30) -> int:
    deadline = time.monotonic() + seconds
    while True:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.status
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def test_the_demo_image_serves_the_editor_and_leaves_nothing(socket_enabled) -> None:
    build = subprocess.run(
        ["docker", "build", "-q", "-f", "dev/docker/Dockerfile", "-t", IMAGE, "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert build.returncode == 0, build.stderr[-2000:]
    name = f"assist-router-demo-test-{uuid.uuid4().hex[:8]}"
    port = free_port()
    publish = ["-p", f"127.0.0.1:{port}:8767"]
    subprocess.run(
        ["docker", "run", "--rm", "--init", "-d", "--name", name, *publish, IMAGE],
        check=True,
        capture_output=True,
    )
    try:
        assert [status(f"http://127.0.0.1:{port}/{page}") for page in PAGES] == [200] * len(PAGES)
    finally:
        subprocess.run(["docker", "stop", "-t", "10", name], capture_output=True, check=False)
    # --rm removes the container a moment after it stops: wait for it
    for _ in range(40):
        left = subprocess.run(
            ["docker", "ps", "-aq", "--filter", f"name={name}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if not left:
            break
        time.sleep(0.5)
    assert left == ""
