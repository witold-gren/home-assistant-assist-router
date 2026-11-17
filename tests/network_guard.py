"""Tests never leave this machine: a connection to anything but 127.0.0.1 (or ::1) fails at once.

A test that reached the real Home Assistant would count as a failed login there (ip_ban),
and a test must not depend on the internet."""

from __future__ import annotations

from collections.abc import Iterator
import socket

import pytest

LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


class LeftThisMachine(OSError):
    """A test tried to connect outside 127.0.0.1."""


def _guarded(real):
    def connect(self: socket.socket, address, *args, **kwargs):
        if self.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in LOOPBACK:
            raise LeftThisMachine(f"tests stay on 127.0.0.1, not {address[0]}")
        return real(self, address, *args, **kwargs)

    return connect


def _true_socket() -> type:
    """Python's own socket class, also while Home Assistant's test plugin swaps in its own."""
    return next(
        cls
        for cls in socket.socket.__mro__
        if cls.__module__ == "socket" and cls.__name__ == "socket"
    )


@pytest.fixture(autouse=True)
def only_this_machine(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every test: sockets connect only to this machine (urllib, aiohttp, asyncio...)."""
    real = _true_socket()
    monkeypatch.setattr(real, "connect", _guarded(real.connect))
    monkeypatch.setattr(real, "connect_ex", _guarded(real.connect_ex))
    yield
