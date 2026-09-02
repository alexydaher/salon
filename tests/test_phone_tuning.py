# SPDX-License-Identifier: GPL-3.0-or-later
"""`GET /tune` and `POST /tune` against a real server on a real socket.

The endpoint writes GSettings on behalf of an HTTP client on the LAN, so
what it refuses matters more than what it accepts. `core/remote_settings`
is tested on its own; this is the half that can only be checked by asking
the server — that the allow-list is actually consulted, that an
unauthenticated request never reaches it, and that a refusal says nothing
about why.
"""

from __future__ import annotations

import json
import os

# GSettings, in memory and nowhere else. A dconf *write* is a D-Bus call to
# the writer daemon, which resolves the user database from its own
# environment, so redirecting the XDG directories is not enough. Assigned
# rather than `setdefault`, and before `gi.repository` is imported, which is
# when the backend is chosen. Enforced by tests/test_settings_isolation.py.
os.environ["GSETTINGS_BACKEND"] = "memory"

import pytest  # noqa: E402

from salon.services.pairing import PairingServer  # noqa: E402
from tests.phone_remote_harness import (  # noqa: E402
    _free_port,
    _get,
    _run,
    _send_full,
)


@pytest.fixture()
def tuned():
    """A server with the tuning callbacks wired to a dictionary."""
    values: dict[str, object] = {
        "accent-color": "#E8A33D",
        "theme": "midnight",
        "tile-scale": 0.55,
        "row-spacing-scale": 0.5,
        "safe-area-percent": 4.5,
        "wallpaper-color-treatment": "automatic",
        "wallpaper-dim": 0.5,
    }
    written: list[tuple[str, object]] = []

    def write(key: str, value: object) -> None:
        written.append((key, value))
        values[key] = value

    server = PairingServer(
        port=_free_port(), tune_read=lambda: dict(values), tune_write=write
    )
    if not server.start():
        pytest.skip("could not bind a local port for the pairing server")
    server.written = written  # type: ignore[attr-defined]
    server.values = values  # type: ignore[attr-defined]
    yield server
    server.stop()


def _settle(server: PairingServer) -> None:
    """Writes are delivered on an idle so the reply can be written first —
    the page flips its own control and the next snapshot confirms it. Give
    the loop a turn before asking what landed."""
    _run(server, lambda: None)


def _read(server: PairingServer) -> dict:
    port = server._port  # noqa: SLF001
    status, body = _run(server, lambda: _get(port, "/tune", k=server.token))
    assert status == 200
    return json.loads(body)


def _write(server: PairingServer, name: str, value: object, *, token: str | None = None) -> int:
    """`key` is the session token — every POST body carries it there — and
    the setting travels as `name`."""
    port = server._port  # noqa: SLF001
    body = {"name": name, "value": value}
    if token is not None:
        body["key"] = token
    return _run(server, lambda: _send_full(port, "/tune", body))[0]


def test_the_phone_is_told_what_it_may_change_and_what_it_is(tuned: PairingServer) -> None:
    payload = _read(tuned)
    keys = {field["key"] for field in payload["fields"]}
    assert keys == set(payload["values"])
    assert payload["values"]["theme"] == "midnight"
    assert payload["values"]["tile-scale"] == pytest.approx(0.55)


def test_an_unauthenticated_read_is_refused(tuned: PairingServer) -> None:
    port = tuned._port  # noqa: SLF001
    status, _body = _run(tuned, lambda: _get(port, "/tune"))
    assert status in (401, 403)
    status, _body = _run(tuned, lambda: _get(port, "/tune", k="not-the-token"))
    assert status in (401, 403)


def test_an_unauthenticated_write_changes_nothing(tuned: PairingServer) -> None:
    assert _write(tuned, "theme", "ember") in (401, 403)
    assert _write(tuned, "theme", "ember", token="not-the-token") in (401, 403)
    assert tuned.written == []  # type: ignore[attr-defined]


def test_a_valid_write_reaches_the_television(tuned: PairingServer) -> None:
    assert _write(tuned, "theme", "ember", token=tuned.token) == 200
    _settle(tuned)
    assert ("theme", "ember") in tuned.written  # type: ignore[attr-defined]


def test_a_range_arrives_clamped_to_its_own_limits(tuned: PairingServer) -> None:
    assert _write(tuned, "tile-scale", 99.0, token=tuned.token) == 200
    _settle(tuned)
    assert tuned.values["tile-scale"] == pytest.approx(1.5)  # type: ignore[attr-defined]


def test_a_key_outside_the_allow_list_is_refused(tuned: PairingServer) -> None:
    """The endpoint never names a GSettings key of its own, so this is the
    whole of what stops it writing one nobody meant to expose."""
    for name in ("remote-desktop-restore-token", "autostart", "onboarding-complete"):
        assert _write(tuned, name, True, token=tuned.token) == 400
    _settle(tuned)
    assert tuned.written == []  # type: ignore[attr-defined]


def test_a_refusal_does_not_say_which_half_was_wrong(tuned: PairingServer) -> None:
    """Distinguishing "no such key" from "value out of range" would
    enumerate the allow-list for anything asking."""
    port = tuned._port  # noqa: SLF001
    unknown = _run(
        tuned, lambda: _send_full(port, "/tune", {"key": tuned.token, "name": "nope", "value": 1})
    )[1]
    bad_value = _run(
        tuned, lambda: _send_full(port, "/tune", {"key": tuned.token, "name": "theme", "value": 7})
    )[1]
    assert unknown == bad_value


def test_a_server_with_no_callbacks_says_so_rather_than_pretending(tuned: PairingServer) -> None:
    bare = PairingServer(port=_free_port())
    if not bare.start():
        pytest.skip("could not bind a second local port")
    try:
        port = bare._port  # noqa: SLF001
        status, _body = _run(bare, lambda: _get(port, "/tune", k=bare.token))
        assert status == 501
    finally:
        bare.stop()
