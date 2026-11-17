"""The guard of tests/network_guard.py: nothing outside 127.0.0.1, this machine still answers."""

from __future__ import annotations

import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from .network_guard import LeftThisMachine


@pytest.fixture(autouse=True)
def sockets(request: pytest.FixtureRequest) -> None:
    """Home Assistant's test plugin turns sockets off; here they are on, behind our guard only."""
    with contextlib.suppress(pytest.FixtureLookupError):
        request.getfixturevalue("socket_enabled")


class _Hello(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_a_connection_outside_this_machine_fails() -> None:
    with pytest.raises((LeftThisMachine, URLError)) as caught:
        urlopen("http://192.168.1.10:8123/", timeout=1)
    assert "tests stay on 127.0.0.1, not 192.168.1.10" in str(caught.value)


def test_this_machine_still_answers() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Hello)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=2) as reply:
            assert reply.read() == b"ok"
    finally:
        server.shutdown()
