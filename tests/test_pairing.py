# SPDX-License-Identifier: GPL-3.0-or-later
"""The phone remote's wire behaviour (§6.12).

Two credentials, doing two jobs, and most of what is asserted here is the
seam between them. The four-digit code is guessable — ten thousand
possibilities, which anything on the same network exhausts in seconds — so
it is accepted at `/connect` and nowhere else, and that one endpoint counts
wrong guesses and burns the session. The session token is 128 bits, is what
every other endpoint takes, and is what the QR code on the television
carries; wrong tokens deliberately do *not* count toward the lockout,
because counting them would turn "cannot be guessed" into "can be locked out
by anyone who can reach the port".

Driven over real HTTP against the real `Soup.Server` rather than by poking
at counters, because the thing being asserted is what a request from the
network actually gets back.

Not a GTK widget test: `PairingServer` is a service with no display, and the
whole point of the exercise is the wire behaviour.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Soup", "3.0")

from gi.repository import GLib  # noqa: E402

from salon.core.remote import RemoteRow, RemoteState, RemoteTile  # noqa: E402
from salon.services.pairing import (  # noqa: E402
    MAX_ATTEMPTS,
    SESSION_TIMEOUT_SECONDS,
    PairingServer,
)

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


@pytest.fixture()
def server():
    typed: list[str] = []
    instance = PairingServer(port=_free_port())
    instance.set_text_sink(typed.append)
    if not instance.start():
        pytest.skip("could not bind a local port for the pairing server")
    yield instance
    instance.stop()


# --- getting in -----------------------------------------------------------


def test_oversized_request_body_is_rejected_before_json_decode(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001
    status, body = _run(server, lambda: _send_bytes(port, "/connect", b"x" * (64 * 1024 + 1)))
    assert status == 413
    assert b"too large" in body.lower()


def test_request_body_at_limit_is_not_rejected_as_too_large(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001
    status, _body = _run(server, lambda: _send_bytes(port, "/connect", b" " * (64 * 1024)))
    assert status != 413


def test_the_right_code_is_exchanged_for_the_session_token(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001 - the fixture picked it
    status, key = _run(server, lambda: _connect(port, server.code))
    assert status == 200
    assert key == server.token
    # 128 bits, url-safe. The point of it is that it is not four digits.
    assert len(key) > 20


def test_the_token_alone_reconnects(server: PairingServer) -> None:
    """The QR path: the phone already holds the token and never sees the
    code. `/connect` still validates it, so a stale code from a previous
    session lands on the code screen instead of on a dead remote."""
    port = server._port  # noqa: SLF001
    assert _run(server, lambda: _connect(port, server.token)) == (200, server.token)


def test_a_stale_token_is_refused(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001
    assert _run(server, lambda: _connect(port, "not-the-token-from-last-time"))[0] == 403


def test_a_wrong_code_is_refused_without_locking_immediately(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001
    wrong = f"{(int(server.code) + 1) % 10000:04d}"
    assert _run(server, lambda: _connect(port, wrong))[0] == 403
    assert not server.locked


def test_repeated_wrong_codes_burn_the_session(server: PairingServer) -> None:
    """The attack this exists for: guessing at machine speed. After the
    allowance, every request is refused — including one with the right
    code, so that stumbling onto it at the boundary wins nothing."""
    port = server._port  # noqa: SLF001
    right = server.code
    wrong = f"{(int(right) + 1) % 10000:04d}"

    def exchange() -> list[int]:
        return [_connect(port, wrong)[0] for _ in range(MAX_ATTEMPTS)] + [
            _connect(port, wrong)[0],
            _connect(port, right)[0],
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
        statuses = [_connect(port, wrong)[0] for _ in range(MAX_ATTEMPTS - 1)]
        statuses.append(_connect(port, right)[0])
        statuses += [_connect(port, wrong)[0] for _ in range(MAX_ATTEMPTS - 1)]
        statuses.append(_connect(port, right)[0])
        return statuses

    statuses = _run(server, exchange)
    assert statuses[MAX_ATTEMPTS - 1] == 200
    assert statuses[-1] == 200
    assert not server.locked


def test_restarting_mints_a_new_code_and_token_and_clears_the_lock(
    server: PairingServer,
) -> None:
    port = server._port  # noqa: SLF001
    old_token = server.token
    wrong = f"{(int(server.code) + 1) % 10000:04d}"
    _run(server, lambda: [_connect(port, wrong)[0] for _ in range(MAX_ATTEMPTS)])
    assert server.locked

    server.stop()
    assert server.start()
    assert not server.locked
    assert len(server.code) == 4
    assert server.token != old_token
    # A fresh session takes its own code again — the lock is per session,
    # not a permanent state of the machine — and the old token is dead.
    port = server._port  # noqa: SLF001
    assert _run(server, lambda: _connect(port, server.code))[0] == 200
    assert _run(server, lambda: _connect(port, old_token))[0] == 403


def test_the_pairing_url_carries_the_token_in_the_fragment(server: PairingServer) -> None:
    """The whole reason scanning is the stronger path: a fragment is never
    sent to a server, so the credential lands in no log."""
    pair_url = server.pair_url
    if pair_url is None:
        pytest.skip("no LAN address on this machine")
    before, _, fragment = pair_url.partition("#")
    assert fragment == f"k={server.token}"
    assert server.token not in before


# --- the page -------------------------------------------------------------


def test_the_page_is_served_without_a_credential(server: PairingServer) -> None:
    """It has to be: the phone needs the page before it can authenticate,
    and nothing in it is a secret — the token arrives in the fragment,
    which never reaches this process."""
    port = server._port  # noqa: SLF001
    status, body = _run(server, lambda: _get(port, "/"))
    assert status == 200
    assert b"<title>Salon</title>" in body


def test_the_manifest_is_served(server: PairingServer) -> None:
    port = server._port  # noqa: SLF001
    status, body = _run(server, lambda: _get(port, "/manifest.webmanifest"))
    assert status == 200
    assert json.loads(body)["short_name"] == "Salon"


@pytest.mark.parametrize(
    ("path", "magic"),
    [("/awake.webm", b"\x1a\x45\xdf\xa3"), ("/awake.mp4", b"ftyp")],
)
def test_the_screen_awake_clips_are_served(
    server: PairingServer, path: str, magic: bytes
) -> None:
    """The phone holds its own screen on by playing these, because
    `navigator.wakeLock` needs a secure context and the remote is HTTP on a
    LAN address. Losing them from the bundle would put the screen back to
    sleep mid-film with nothing on screen to say why, so it is worth a test
    that they are really there and really playable."""
    port = server._port  # noqa: SLF001
    status, body = _run(server, lambda: _get(port, path))
    assert status == 200
    assert magic in body[:32]


# --- the remote -----------------------------------------------------------


@pytest.fixture()
def remote(tmp_path):
    """A server wired the way the home screen wires it: buttons, a
    trackpad, a catalogue and a launcher, and no text field on screen
    asking for anything."""
    received: dict[str, list] = {
        "actions": [],
        "motion": [],
        "clicks": [],
        "launched": [],
        "transport": [],
        "searched": [],
        "tile_actions": [],
        "volume": [],
        "scroll": [],
        "buttons": [],
    }
    poster = tmp_path / "poster.png"
    poster.write_bytes(b"\x89PNG\r\n\x1a\n not really a png, but it is bytes")

    def searched(query: str) -> list[RemoteTile]:
        received["searched"].append(query)
        if query == "nothing":
            return []
        return [RemoteTile(id="app:gimp.desktop", title="GIMP")]

    def tile_action(tile_id: str, what: str) -> str:
        received["tile_actions"].append((tile_id, what))
        return f"{what} {tile_id}"

    instance = PairingServer(
        port=_free_port(),
        on_action=received["actions"].append,
        on_pointer=lambda dx, dy: received["motion"].append((dx, dy)),
        on_click=lambda: received["clicks"].append(True),
        on_launch=received["launched"].append,
        on_transport=lambda what: bool(received["transport"].append(what)) or True,
        art_for=lambda tile_id: poster if tile_id in ("netflix", "app:gimp.desktop") else None,
        on_search=searched,
        on_tile_action=tile_action,
        on_volume=received["volume"].append,
        on_mute=lambda: received["volume"].append("mute"),
        on_scroll=lambda dx, dy: received["scroll"].append((dx, dy)),
        on_scroll_end=lambda: received["scroll"].append("end"),
        on_button=lambda button, what: received["buttons"].append((button, what)),
    )
    instance.publish(
        RemoteState(
            rows=(
                RemoteRow(
                    id="streaming",
                    title="Streaming",
                    tiles=(
                        RemoteTile(id="netflix", title="Netflix", has_art=True),
                        RemoteTile(id="iplayer", title="iPlayer"),
                    ),
                ),
            )
        )
    )
    if not instance.start():
        pytest.skip("could not bind a local port for the pairing server")
    yield instance, received
    instance.stop()


def test_a_button_press_arrives_as_an_action(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server, lambda: _send(port, "/action", {"key": server.token, "action": "menu"})
    ) == 200
    assert received["actions"] == ["menu"]


def test_the_token_gates_every_endpoint(remote) -> None:
    """The point of a credential is lost if any one door skips it."""
    server, received = remote
    port = server._port  # noqa: SLF001

    def exchange() -> list[int]:
        return [
            _send(port, "/action", {"key": "", "action": "menu"}),
            _send(port, "/pointer", {"key": "", "dx": 10, "dy": 10}),
            _send(port, "/pointer", {"key": "", "click": True}),
            _send(port, "/pointer", {"key": "", "sx": 4, "sy": 4}),
            _send(port, "/pointer", {"key": "", "hold": "down", "button": "left"}),
            _send(port, "/type", {"key": "", "text": "hello"}),
            _send(port, "/launch", {"key": "", "id": "netflix"}),
            _send(port, "/transport", {"key": "", "what": "play_pause"}),
            _send(port, "/search", {"key": "", "q": "net"}),
            _send(port, "/tile", {"key": "", "id": "netflix", "what": "pin"}),
            _send(port, "/volume", {"key": "", "level": 0.5}),
            _get(port, "/state")[0],
            _get(port, "/art/netflix")[0],
            _get(port, "/events")[0],
        ]

    assert _run(server, exchange) == [401] * 14
    # Not "no actions arrived" — *nothing* arrived, on any callback the home
    # screen hands this server. Written as an equality against the whole
    # record so that a new endpoint wired up without a credential fails here
    # rather than shipping.
    assert received == {
        "actions": [],
        "motion": [],
        "clicks": [],
        "launched": [],
        "transport": [],
        "searched": [],
        "tile_actions": [],
        "volume": [],
        "scroll": [],
        "buttons": [],
    }


def test_a_wrong_token_never_burns_the_session(remote) -> None:
    """The reason wrong tokens are not counted.

    A 128-bit secret is not going to be guessed, so counting failures on
    that path buys nothing — while handing anyone who can reach the port a
    way to lock out the phone that is legitimately paired. Spraying garbage
    tokens has to be inert.
    """
    server, _received = remote
    port = server._port  # noqa: SLF001

    def exchange() -> list[int]:
        junk = [
            _send(port, "/action", {"key": "wrong-token", "action": "menu"})
            for _ in range(MAX_ATTEMPTS * 4)
        ]
        return junk + [_send(port, "/action", {"key": server.token, "action": "menu"})]

    statuses = _run(server, exchange)
    assert set(statuses[:-1]) == {401}
    assert statuses[-1] == 200
    assert not server.locked


def test_an_unknown_button_is_refused_rather_than_ignored(remote) -> None:
    """A page and an enum edited in different files drift; a silent no-op
    would show up as a button that does nothing for no stated reason."""
    server, received = remote
    port = server._port  # noqa: SLF001
    status = _run(
        server,
        lambda: _send(port, "/action", {"key": server.token, "action": "self_destruct"}),
    )
    assert status == 400
    assert received["actions"] == []


def test_the_trackpad_moves_and_taps(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001

    def exchange() -> list[int]:
        return [
            _send(port, "/pointer", {"key": server.token, "dx": 12.5, "dy": -3.0}),
            _send(port, "/pointer", {"key": server.token, "click": True}),
        ]

    assert _run(server, exchange) == [200, 200]
    assert received["motion"] == [(12.5, -3.0)]
    assert received["clicks"] == [True]


def test_nonsense_motion_is_clamped_not_forwarded(remote) -> None:
    """A cursor sent to infinity never comes back, and JSON carries
    Infinity and NaN whatever the specification says."""
    server, received = remote
    port = server._port  # noqa: SLF001

    def exchange() -> list[int]:
        return [
            _send(port, "/pointer", {"key": server.token, "dx": 1e9, "dy": 0}),
            _send(port, "/pointer", {"key": server.token, "dx": float("inf"), "dy": 0}),
            _send(port, "/pointer", {"key": server.token, "dx": "over there", "dy": 0}),
        ]

    assert _run(server, exchange) == [200, 200, 200]
    # The huge one is clamped and delivered; the other two are not numbers
    # at all and contribute nothing.
    assert received["motion"] == [(2000.0, 0.0)]


def test_text_with_nowhere_to_go_says_so(remote) -> None:
    """The phone is holding a keyboard for a field that is not on screen.
    Silence there is indistinguishable from a dropped connection."""
    server, _received = remote
    port = server._port  # noqa: SLF001
    assert _run(server, lambda: _post(port, server.token, "hello")) == 409


def test_holds_are_counted_so_two_screens_cannot_stop_each_other(remote) -> None:
    """The remote and an open text field both want the phone. Whichever is
    dismissed first must not take the port with it."""
    server, _received = remote
    server.acquire("phone-remote")
    server.acquire("keyboard-1")
    server.release("keyboard-1")
    assert server.running
    server.release("phone-remote")
    assert not server.running


# --- the second screen ----------------------------------------------------


def test_the_state_poll_answers_once_and_then_says_nothing_changed(remote) -> None:
    """The phone polls once a second and this handler runs on the same main
    loop that animates the tiles, so an unchanged poll has to be free."""
    server, _received = remote
    port = server._port  # noqa: SLF001

    first = _run(server, lambda: _get(port, "/state", k=server.token, v="0"))
    assert first[0] == 200
    state = json.loads(first[1])
    assert [row["title"] for row in state["rows"]] == ["Streaming"]
    assert [tile["id"] for tile in state["rows"][0]["tiles"]] == ["netflix", "iplayer"]

    again = _run(server, lambda: _get(port, "/state", k=server.token, v=str(state["v"])))
    assert again == (204, b"")


def test_a_new_snapshot_bumps_the_version(remote) -> None:
    server, _received = remote
    port = server._port  # noqa: SLF001
    first = json.loads(_run(server, lambda: _get(port, "/state", k=server.token, v="0"))[1])

    assert server.publish(RemoteState(screen="settings"))
    second = _run(server, lambda: _get(port, "/state", k=server.token, v=str(first["v"])))
    assert second[0] == 200
    assert json.loads(second[1])["screen"] == "settings"


def test_a_tile_can_be_launched_by_id(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    status = _run(server, lambda: _send(port, "/launch", {"key": server.token, "id": "netflix"}))
    assert status == 200
    assert received["launched"] == ["netflix"]


def test_only_what_the_phone_was_shown_can_be_launched(remote) -> None:
    """The phone is a second remote, not a second way in: an id it was
    never given is refused rather than looked up."""
    server, received = remote
    port = server._port  # noqa: SLF001

    def exchange() -> list[int]:
        return [
            _send(port, "/launch", {"key": server.token, "id": "something-else"}),
            _send(port, "/launch", {"key": server.token, "id": "../../etc/passwd"}),
        ]

    assert _run(server, exchange) == [404, 404]
    assert received["launched"] == []


def test_artwork_is_served_for_a_published_tile_and_nothing_else(remote) -> None:
    server, _received = remote
    port = server._port  # noqa: SLF001

    ok = _run(server, lambda: _get(port, "/art/netflix", k=server.token))
    assert ok[0] == 200
    assert ok[1].startswith(b"\x89PNG")

    # A tile with no file behind it, and an id that was never published.
    assert _run(server, lambda: _get(port, "/art/iplayer", k=server.token))[0] == 404
    assert _run(server, lambda: _get(port, "/art/passwd", k=server.token))[0] == 404


def test_transport_controls_reach_the_player(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001

    def exchange() -> list[int]:
        return [
            _send(port, "/transport", {"key": server.token, "what": "play_pause"}),
            _send(port, "/transport", {"key": server.token, "what": "next"}),
            _send(port, "/transport", {"key": server.token, "what": "sing"}),
        ]

    assert _run(server, exchange) == [200, 200, 400]
    assert received["transport"] == ["play_pause", "next"]


# --- typing into something that isn't Salon -------------------------------


@pytest.fixture()
def injecting():
    """A server wired the way the home screen wires it once the desktop has
    granted Salon its input devices: no Salon field is asking for text, but
    there is a launched application to type into."""
    typed: list[str] = []
    instance = PairingServer(
        port=_free_port(),
        on_remote_text=lambda text: bool(typed.append(text)) or True,
    )
    if not instance.start():
        pytest.skip("could not bind a local port for the pairing server")
    yield instance, typed
    instance.stop()


def test_text_with_no_salon_field_goes_to_the_focused_application(injecting) -> None:
    """The phone keyboard's whole point on a television is the one text box
    Salon cannot draw: a search field inside a launched browser."""
    server, typed = injecting
    port = server._port  # noqa: SLF001
    assert _run(server, lambda: _post(port, server.token, "blue monday")) == 200
    assert typed == ["blue monday"]


def test_a_salon_field_still_wins_over_the_application(injecting) -> None:
    """Search is on screen; the phone is typing into search, not past it."""
    server, typed = injecting
    into_salon: list[str] = []
    server.set_text_sink(into_salon.append)
    port = server._port  # noqa: SLF001
    assert _run(server, lambda: _post(port, server.token, "hello")) == 200
    assert into_salon == ["hello"]
    assert typed == []


def test_text_with_nowhere_at_all_to_go_explains_itself(remote) -> None:
    """No Salon field and no input grant. The refusal names the setting
    that would fix it, because a keyboard that silently does nothing is
    indistinguishable from a dropped connection."""
    server, _received = remote
    port = server._port  # noqa: SLF001
    status, body = _run(server, lambda: _send_full(port, "/type", {"key": server.token,
                                                                   "text": "hello"}))
    assert status == 409
    assert b"Gamepad cursor" in body


# --- staying connected ----------------------------------------------------


def test_a_held_session_does_not_time_out(remote) -> None:
    """A phone with its screen off sends nothing. Treating that as "nobody
    wants the remote" is how it switched itself off mid-film — so while
    something holds it, the idle check never fires."""
    server, _received = remote
    server.acquire("phone-remote")
    server._last_seen = time.monotonic() - (SESSION_TIMEOUT_SECONDS * 10)  # noqa: SLF001
    assert server._check_idle()  # noqa: SLF001 - GLib.SOURCE_CONTINUE
    assert server.running
    assert server.token


def test_an_unheld_session_still_times_out(server: PairingServer) -> None:
    """The protection that timeout was written for is still there for a
    session nobody claimed."""
    assert not server.holds("phone-remote")
    server._last_seen = time.monotonic() - (SESSION_TIMEOUT_SECONDS * 2)  # noqa: SLF001
    assert not server._check_idle()  # noqa: SLF001 - GLib.SOURCE_REMOVE
    assert not server.running


# --- search ----------------------------------------------------------------


def test_search_returns_tiles_in_the_shape_the_page_draws(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    status, body = _run(
        server, lambda: _send_full(port, "/search", {"key": server.token, "q": "gim"})
    )
    assert status == 200
    assert received["searched"] == ["gim"]
    results = json.loads(body)["results"]
    assert [tile["id"] for tile in results] == ["app:gimp.desktop"]
    # The same keys a catalogue tile carries, so one card renders both.
    assert set(results[0]) >= {"id", "title", "accent", "art", "fit", "pinned", "removable"}


def test_a_search_result_can_then_be_launched_and_its_art_fetched(remote) -> None:
    """The invariant is "what the phone has been shown", not "what is on the
    television" — and a result it was just handed is squarely the former."""
    server, received = remote
    port = server._port  # noqa: SLF001

    # Before the search, an id the phone has never seen is refused.
    assert _run(
        server,
        lambda: _send(port, "/launch", {"key": server.token, "id": "app:gimp.desktop"}),
    ) == 404

    assert _run(
        server, lambda: _send(port, "/search", {"key": server.token, "q": "gim"})
    ) == 200
    assert _run(
        server,
        lambda: _send(port, "/launch", {"key": server.token, "id": "app:gimp.desktop"}),
    ) == 200
    assert received["launched"] == ["app:gimp.desktop"]

    status, _ = _run(
        server, lambda: _get(port, "/art/app%3Agimp.desktop", k=server.token)
    )
    assert status == 200


def test_an_id_never_offered_is_still_refused(remote) -> None:
    server, _ = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server, lambda: _send(port, "/search", {"key": server.token, "q": "gim"})
    ) == 200
    assert _run(
        server, lambda: _send(port, "/launch", {"key": server.token, "id": "/etc/passwd"})
    ) == 404


def test_stopping_forgets_what_was_offered(remote) -> None:
    """A new session starts knowing nothing about the last one's results."""
    server, _ = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server, lambda: _send(port, "/search", {"key": server.token, "q": "gim"})
    ) == 200
    assert "app:gimp.desktop" in server._offered  # noqa: SLF001
    server.stop()
    assert "app:gimp.desktop" not in server._offered  # noqa: SLF001


# --- the per-tile menu ------------------------------------------------------


def test_a_tile_action_reaches_the_television_and_answers_with_a_sentence(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    status, body = _run(
        server,
        lambda: _send_full(port, "/tile", {"key": server.token, "id": "netflix", "what": "pin"}),
    )
    assert status == 200
    assert received["tile_actions"] == [("netflix", "pin")]
    assert json.loads(body)["said"] == "pin netflix"


def test_an_unknown_tile_action_is_refused(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server,
        lambda: _send(port, "/tile", {"key": server.token, "id": "netflix", "what": "rm -rf"}),
    ) == 400
    assert received["tile_actions"] == []


def test_a_tile_action_on_something_never_shown_is_refused(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server,
        lambda: _send(port, "/tile", {"key": server.token, "id": "nope", "what": "pin"}),
    ) == 404
    assert received["tile_actions"] == []


# --- volume -----------------------------------------------------------------


def test_the_slider_sets_an_absolute_level(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server, lambda: _send(port, "/volume", {"key": server.token, "level": 0.42})
    ) == 200
    assert received["volume"] == [pytest.approx(0.42)]


def test_a_level_off_the_end_of_the_slider_is_clamped(remote) -> None:
    """It arrives from a network endpoint, so 9000% has to mean 100%."""
    server, received = remote
    port = server._port  # noqa: SLF001
    for sent in (90.0, -3.0):
        assert _run(
            server, lambda level=sent: _send(port, "/volume", {"key": server.token, "level": level})
        ) == 200
    assert received["volume"] == [1.0, 0.0]


def test_mute_is_its_own_field(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server, lambda: _send(port, "/volume", {"key": server.token, "mute": True})
    ) == 200
    assert received["volume"] == ["mute"]


# --- the trackpad's gestures ------------------------------------------------


def test_two_fingers_scroll(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server, lambda: _send(port, "/pointer", {"key": server.token, "sx": 0.0, "sy": -14.0})
    ) == 200
    assert received["scroll"] == [(0.0, -14.0)]
    assert received["motion"] == []


def test_lifting_the_fingers_finishes_the_scroll(remote) -> None:
    """`finish` is what stops kinetic scrolling drifting on after the
    gesture ends; without it a flick keeps going."""
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server, lambda: _send(port, "/pointer", {"key": server.token, "scrollEnd": True})
    ) == 200
    assert received["scroll"] == ["end"]


def test_a_two_finger_tap_is_a_right_click(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server,
        lambda: _send(port, "/pointer", {"key": server.token, "click": True, "button": "right"}),
    ) == 200
    assert received["buttons"] == [("right", "click")]
    # The left button keeps its own callback, so the plain tap path is
    # untouched by any of this.
    assert received["clicks"] == []


def test_a_bare_click_is_still_the_left_button(remote) -> None:
    """An older page, cached on somebody's phone, sends no button at all."""
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server, lambda: _send(port, "/pointer", {"key": server.token, "click": True})
    ) == 200
    assert received["clicks"] == [True]


def test_a_button_can_be_held_down_and_let_go(remote) -> None:
    """What a drag needs: a click that releases itself 50ms later cannot
    move a window or select a line of text."""
    server, received = remote
    port = server._port  # noqa: SLF001
    for what in ("down", "up"):
        assert _run(
            server,
            lambda w=what: _send(
                port, "/pointer", {"key": server.token, "hold": w, "button": "left"}
            ),
        ) == 200
    assert received["buttons"] == [("left", "down"), ("left", "up")]


def test_an_unknown_mouse_button_is_refused(remote) -> None:
    server, received = remote
    port = server._port  # noqa: SLF001
    assert _run(
        server,
        lambda: _send(port, "/pointer", {"key": server.token, "click": True, "button": "fourth"}),
    ) == 400
    assert received["buttons"] == []
    assert received["clicks"] == []


# --- the event stream -------------------------------------------------------


def _read_event(sock: socket.socket, deadline: float) -> str:
    """Read until one complete `data:` frame has arrived, or time runs out."""
    buffered = b""
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except (TimeoutError, OSError):
            break
        if not chunk:
            break
        buffered += chunk
        if b"data: " in buffered and buffered.rstrip().endswith(b"}"):
            break
    return buffered.decode("utf-8", "replace")


def test_the_event_stream_pushes_state_without_being_asked(remote) -> None:
    """The whole reason it exists: a press changes the television now, and
    the poll cannot find out for up to a second.

    What this pins down is that libsoup's server will hold a response open
    and let later writes reach the socket at all — the thing the whole
    feature rests on, and the thing that is not obvious from the API. It
    fails by timing out with an empty read.
    """
    server, _ = remote
    port = server._port  # noqa: SLF001

    def exchange() -> str:
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        sock.settimeout(1.0)
        sock.sendall(
            f"GET /events?k={server.token} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Accept: text/event-stream\r\n\r\n".encode()
        )
        deadline = time.monotonic() + 5
        opening = _read_event(sock, deadline)
        # A change on the television, from the thread that owns the loop.
        GLib.idle_add(
            lambda: bool(server.publish(RemoteState(screen="settings", app="", volume=0.5)))
            and False
        )
        pushed = _read_event(sock, time.monotonic() + 5)
        sock.close()
        return opening + pushed

    text = _run(server, exchange)
    assert "text/event-stream" in text
    # The state as it stood when the stream opened, so a phone that has just
    # connected draws the television rather than an empty page.
    assert text.count("data: ") >= 2
    assert '"screen":"settings"' in text


def test_the_stream_is_dropped_when_the_server_stops(remote) -> None:
    server, _ = remote
    port = server._port  # noqa: SLF001

    def exchange() -> int:
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        sock.settimeout(2.0)
        sock.sendall(
            f"GET /events?k={server.token} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n\r\n".encode()
        )
        _read_event(sock, time.monotonic() + 3)
        held = len(server._streams)  # noqa: SLF001
        sock.close()
        return held

    assert _run(server, exchange) == 1
