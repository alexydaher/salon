# SPDX-License-Identifier: GPL-3.0-or-later
"""Talking to a real `PairingServer` over real HTTP, from a test.

`Soup.Server` dispatches on the main context, so a request cannot be made
from the thread that has to answer it — every exchange runs on a worker
while `_run` spins a GLib loop. Shared by the wire tests rather than
copied into each, because the loop-and-worker dance is the part that is
easy to get subtly wrong.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Soup", "3.0")

from gi.repository import GLib  # noqa: E402

from salon.services.pairing import PairingServer  # noqa: E402

_TIMEOUT_SECONDS = 10


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _send(port: int, path: str, payload: dict) -> int:
    """The status a phone would see. Never an exception."""
    return _send_full(port, path, payload)[0]


def _send_full(port: int, path: str, payload: dict) -> tuple[int, bytes]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()


def _send_bytes(port: int, path: str, payload: bytes) -> tuple[int, bytes]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()


def _get(port: int, path: str, **params: str) -> tuple[int, bytes]:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}{query}", timeout=5) as r:
            return int(r.status), r.read()
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()


def _connect(port: int, credential: str) -> tuple[int, str]:
    """Exchange a code (or a token) for the session token."""
    field = "code" if credential.isdigit() and len(credential) == 4 else "key"
    status, body = _send_full(port, "/connect", {field: credential})
    if status != 200:
        return status, ""
    return status, str(json.loads(body)["key"])


def _post(port: int, key: str, text: str) -> int:
    return _send(port, "/type", {"key": key, "text": text})


def _run(server: PairingServer, exchange):
    """Run `exchange` off the main thread while the GLib loop serves it.

    Soup.Server dispatches on the main context, so the requests cannot be
    made from the same thread that has to answer them.
    """
    loop = GLib.MainLoop()
    result: list = []

    def worker() -> None:
        try:
            result.append(exchange())
        finally:
            GLib.idle_add(loop.quit)

    thread = threading.Thread(target=worker, daemon=True)
    GLib.timeout_add_seconds(_TIMEOUT_SECONDS, loop.quit)
    thread.start()
    loop.run()
    thread.join(timeout=1)
    return result[0] if result else None
