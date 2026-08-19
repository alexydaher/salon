# SPDX-License-Identifier: GPL-3.0-or-later
"""The phone keyboard's brute-force lockout (§6.12).

The pairing code is four digits — ten thousand possibilities, which anything
on the same network exhausts in seconds. `compare_digest` in the handler
defeats a timing oracle and nothing else, so the server has to stop
answering. This drives the real `Soup.Server` over real HTTP rather than
poking at the counter, because the thing being asserted is what a request
from the network actually gets back.

Not a GTK widget test: `PairingServer` is a service with no display, and the
whole point of the exercise is the wire behaviour.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Soup", "3.0")

from gi.repository import GLib  # noqa: E402

from salon.services.pairing import MAX_ATTEMPTS, PairingServer  # noqa: E402

_TIMEOUT_SECONDS = 10


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _post(port: int, code: str, text: str) -> int:
    """The status a phone would see. 200, 403 or 429 — never an exception."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/type",
        data=json.dumps({"code": code, "text": text}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def _run(server: PairingServer, exchange) -> list[int]:
    """Run `exchange` off the main thread while the GLib loop serves it.

    Soup.Server dispatches on the main context, so the requests cannot be
    made from the same thread that has to answer them.
    """
    loop = GLib.MainLoop()
    statuses: list[int] = []

    def worker() -> None:
        try:
            statuses.extend(exchange())
        finally:
            GLib.idle_add(loop.quit)

    thread = threading.Thread(target=worker, daemon=True)
    GLib.timeout_add_seconds(_TIMEOUT_SECONDS, loop.quit)
    thread.start()
    loop.run()
    thread.join(timeout=1)
    return statuses


@pytest.fixture()
def server():
    typed: list[str] = []
    instance = PairingServer(typed.append, port=_free_port())
    if not instance.start():
        pytest.skip("could not bind a local port for the pairing server")
    yield instance
    instance.stop()


def test_the_right_code_is_accepted(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001 - the fixture picked it
    statuses = _run(server, lambda: [_post(port, server.code, "hello")])
    assert statuses == [200]


def test_a_wrong_code_is_refused_without_locking_immediately(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001
    wrong = f"{(int(server.code) + 1) % 10000:04d}"
    statuses = _run(server, lambda: [_post(port, wrong, "nope")])
    assert statuses == [403]
    assert not server.locked


def test_repeated_wrong_codes_burn_the_session(server: PairingServer) -> None:
    """The attack this exists for: guessing at machine speed. After the
    allowance, every request is refused — including one with the right
    code, so that stumbling onto it at the boundary wins nothing."""
    port = server._port  # noqa: SLF001
    right = server.code
    wrong = f"{(int(right) + 1) % 10000:04d}"

    def exchange() -> list[int]:
        return [_post(port, wrong, "nope") for _ in range(MAX_ATTEMPTS)] + [
            _post(port, wrong, "nope"),
            _post(port, right, "should not be typed"),
        ]

    statuses = _run(server, exchange)
    assert statuses[:MAX_ATTEMPTS] == [403] * MAX_ATTEMPTS
    assert statuses[MAX_ATTEMPTS:] == [429, 429]
    assert server.locked


def test_a_correct_code_clears_the_count(server: PairingServer) -> None:
    """Someone mistyping four digits on a phone must not be one fumble away
    from having to walk to the television."""
    port = server._port  # noqa: SLF001
    right = server.code
    wrong = f"{(int(right) + 1) % 10000:04d}"

    def exchange() -> list[int]:
        statuses = [_post(port, wrong, "nope") for _ in range(MAX_ATTEMPTS - 1)]
        statuses.append(_post(port, right, "hello"))
        statuses += [_post(port, wrong, "nope") for _ in range(MAX_ATTEMPTS - 1)]
        statuses.append(_post(port, right, "still fine"))
        return statuses

    statuses = _run(server, exchange)
    assert statuses[MAX_ATTEMPTS - 1] == 200
    assert statuses[-1] == 200
    assert not server.locked


def test_restarting_mints_a_new_code_and_clears_the_lock(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001
    wrong = f"{(int(server.code) + 1) % 10000:04d}"
    _run(server, lambda: [_post(port, wrong, "nope") for _ in range(MAX_ATTEMPTS)])
    assert server.locked

    server.stop()
    assert server.start()
    assert not server.locked
    assert len(server.code) == 4
    # A fresh session takes the right code again — the lock is per session,
    # not a permanent state of the machine.
    port = server._port  # noqa: SLF001
    assert _run(server, lambda: [_post(port, server.code, "hello")]) == [200]
