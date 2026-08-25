# SPDX-License-Identifier: GPL-3.0-or-later
"""Phone-as-remote over the LAN (§6.12).

Text entry with a D-pad is the worst part of any TV interface, and this
started as the escape hatch for it: the screen shows a URL and a four-digit
code, the phone opens one page, and what it types arrives in Salon's
focused entry.

It is now a **second screen**. The page carries a D-pad, OK/Back/Menu/
Options/Search, volume, a trackpad, the whole catalogue with its artwork,
and transport controls for whatever is playing. Buttons post an `Action`,
which is the only input currency Salon has, so the phone is not a special
case anywhere above this file: it is a fourth input source alongside the
keyboard, the gamepad and CEC. Tiles post an id, which goes through the
same launch path as a press on the television.

The trackpad posts relative motion straight into the RemoteDesktop pointer
session, which is what makes a phone useful over a browser-hosted tile that
was never designed for a remote at all.

## Credentials: a code to get in, a token to stay

There are two secrets and they do different jobs.

The **four-digit code** is a bootstrap credential and is accepted at
`/connect` and nowhere else. Four digits is ten thousand possibilities,
which a script on the same network exhausts in seconds, so that one
endpoint counts wrong codes and burns the session after `MAX_ATTEMPTS` —
including for the right code afterwards, so guessing it on the last allowed
attempt wins nothing.

The **session token** is 128 bits from `secrets`, and is what every other
request carries. It is minted with the session, returned by `/connect`, and
— this is the point — **encoded in the QR code shown on the television**,
in the URL *fragment*. A fragment is never sent to the server, so scanning
the code off the screen puts the secret in no access log, no `Referer` and
no proxy's history; the page reads it out of `location.hash` and strips it
from the address bar. Scanning is therefore not merely more convenient than
typing four digits, it is the stronger of the two paths, and the weak
secret exists only for someone who typed the URL by hand.

Wrong *tokens* are deliberately **not** counted toward the lockout. A
128-bit secret is not going to be guessed, and counting failures on that
path would hand anyone within reach of the port a way to lock out the phone
that is legitimately paired — trading an attack that cannot succeed for one
that trivially can.

## The rest of the properties, all load-bearing

* **On demand only.** The server starts when a text field asks for it, or
  when the remote is switched on in Settings, and stops when the last of
  those goes away. A launcher that quietly runs an HTTP server on the LAN
  for its whole lifetime is not something to ship — and the remote setting
  deliberately does not survive a restart, so a reboot never silently
  reopens the port.
* **Local sources only.** Every request is checked against
  `core.remote.is_local_address` before its credential is even read. This
  is plaintext HTTP by design (see below); that trade is only defensible
  while "on the same network" means something, and on a dual-homed host, or
  one that ends up with a public address it did not expect, this is the
  difference between a remote and an open door.
* **An unheld session expires.** Five minutes of *inactivity*, enforced
  server-side, so a session nobody claimed can't be left open. A session
  that *is* held — the remote you switched on — does not time out, and that
  is a deliberate reversal: the timeout was written when this was a
  keyboard you summoned for one URL, and it meant a remote quietly switching
  itself off forty minutes into a film, because the phone stops polling
  while its screen is off. A mode the user turned on is a mode the user
  turns off. It still does not survive a restart, so a reboot never
  silently reopens the port.
* **The phone can only reach what is on screen.** `/launch` and `/art`
  resolve ids against the tile ids in the *published state* — the ones the
  phone was shown — rather than against the catalogue or the filesystem.
  An id it was never given is refused rather than looked up.

## What this is not

It is HTTP. The code and the token stop a stranger *sending* something;
they do not stop anyone already on the same network from *reading* it. TLS
was considered and rejected: a self-signed certificate produces a browser
interstitial, which destroys the one-scan path this is built around, and
there is no certificate authority that will issue for `192.168.1.151`.
Documented in the README rather than pretended away.

It also does not solve OAuth inside a spawned Chrome — that happens in
another process, outside Salon's control.
"""

from __future__ import annotations

import json
import secrets
import socket
import time
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Soup", "3.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib, Soup  # noqa: E402

from salon.core.remote import (  # noqa: E402
    OfferedIds,
    RemoteState,
    RemoteTile,
    StateFeed,
    is_local_address,
)
from salon.input.actions import Action  # noqa: E402

# What the page is allowed to ask for. Derived from the enum rather than
# written out again, so a button added to the page and an Action added to
# the vocabulary cannot drift apart — the failure mode of a hand-kept list
# here is a button that posts something Salon silently ignores.
ACTION_NAMES = frozenset(action.value for action in Action)

# The three things you can do to a player. Not Actions: see the comment on
# the transport buttons in the page.
TRANSPORT_NAMES = frozenset({"play_pause", "next", "previous"})

# What the per-tile menu on the phone may ask for. Pinning and unpinning
# write `favourite-tile-ids`; "edit" opens the television's own tile editor
# on that tile, because a form with eight fields is not something to
# reimplement on a phone; "remove" deletes it from `tiles.json` and is only
# offered for a tile that came from there.
TILE_ACTIONS = frozenset({"pin", "unpin", "edit", "remove"})

# Mouse buttons the trackpad can send. Names rather than evdev codes on the
# wire: the page should not have to know that the middle button is 0x112,
# and an unknown name is refused rather than passed through to the portal.
POINTER_BUTTONS = frozenset({"left", "right", "middle"})

# The most results a search will return. A phone screen shows about six at a
# time and nobody scrolls a remote control; past this the ranking is doing
# no work that anyone reads.
MAX_SEARCH_RESULTS = 40

DEFAULT_PORT = 8437
SESSION_TIMEOUT_SECONDS = 300

# How often the idle deadline is checked. A repeating timer that compares a
# monotonic stamp, rather than a timeout rescheduled per request: the phone
# polls once a second, and tearing down and rebuilding a GLib source at that
# rate to express "still here" is work for nothing.
_IDLE_CHECK_SECONDS = 15

# How long after the last authenticated request a phone still counts as
# connected. A little over the page's one-second poll, so a phone sitting on
# the remote reads as present without flickering between polls.
_CONNECTED_SECONDS = 4.0

# Wrong codes allowed before the session is burned. Low enough that a brute
# force gets nowhere, high enough to survive a person mistyping four digits
# on a phone keyboard a few times.
MAX_ATTEMPTS = 5

# 128 bits. `token_urlsafe(16)` is 22 characters, which keeps the pairing
# URL inside QR version 4 at error-correction level M — comfortably within
# what core/qr.py encodes and what a camera reads off a television.
_TOKEN_BYTES = 16

# Soup.Status has no TOO_MANY_REQUESTS member in libsoup 3.
_STATUS_TOO_MANY_REQUESTS = 429

# Artwork is read off disk on the main loop, so a pathological file must not
# become a stall. Nothing legitimate here is close to this: the largest
# thing served is a cached poster.
_MAX_ART_BYTES = 8 * 1024 * 1024

_ART_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}

# The blank loop the page plays to hold a phone's screen on, in the two
# containers between them cover every phone: Safari wants H.264, and VP8 has
# been on Android for longer than anything else. See the `#awake` element.
_AWAKE_CLIPS = {
    "/awake.webm": ("awake.webm", "video/webm"),
    "/awake.mp4": ("awake.mp4", "video/mp4"),
}


def local_address() -> str | None:
    """The address a phone on the same LAN can actually reach.

    Connecting a UDP socket to an off-link address doesn't send anything;
    it just makes the kernel pick the route it would use, which is the only
    reliable way to find the right interface on a host with several.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed anywhere
        return str(probe.getsockname()[0])
    except OSError:
        return None
    finally:
        probe.close()


def _resource_bytes(name: str) -> bytes | None:
    """One of the page's static files out of the GResource bundle.

    Falls back to the source tree, twice over, and both fallbacks are load
    bearing for the same reason: `PairingServer` is a service with no
    display, and the tests drive it without an application — but it is
    `app.py` that registers the bundle, and `salon/config.py` is generated
    by Meson into the build tree and does not exist in a bare checkout. An
    installed Salon takes the first path every time.
    """
    try:
        from salon import config as app_config

        data = Gio.resources_lookup_data(
            f"{app_config.RESOURCE_BASE_PATH}/remote/{name}", Gio.ResourceLookupFlags.NONE
        )
        return bytes(data.get_data() or b"")
    except (ImportError, GLib.Error):
        pass
    local = Path(__file__).resolve().parents[2] / "data" / "remote" / name
    try:
        return local.read_bytes()
    except OSError:
        return None


class PairingServer:
    """Serves the remote page, and everything it can ask for."""

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        *,
        on_action: Callable[[str], None] | None = None,
        on_pointer: Callable[[float, float], None] | None = None,
        on_click: Callable[[], None] | None = None,
        on_locked: Callable[[], None] | None = None,
        on_launch: Callable[[str], None] | None = None,
        on_transport: Callable[[str], bool] | None = None,
        art_for: Callable[[str], Path | None] | None = None,
        pointer_ready: Callable[[], bool] | None = None,
        on_remote_text: Callable[[str], bool] | None = None,
        on_search: Callable[[str], list[RemoteTile]] | None = None,
        on_tile_action: Callable[[str, str], str] | None = None,
        on_volume: Callable[[float], None] | None = None,
        on_mute: Callable[[], None] | None = None,
        on_scroll: Callable[[float, float], None] | None = None,
        on_scroll_end: Callable[[], None] | None = None,
        on_button: Callable[[str, str], None] | None = None,
    ) -> None:
        self._on_action = on_action
        self._on_pointer = on_pointer
        self._on_click = on_click
        self._on_locked = on_locked
        self._on_launch = on_launch
        self._on_transport = on_transport
        self._art_for = art_for
        self._pointer_ready = pointer_ready
        self._on_remote_text = on_remote_text
        self._on_search = on_search
        self._on_tile_action = on_tile_action
        self._on_volume = on_volume
        self._on_mute = on_mute
        self._on_scroll = on_scroll
        self._on_scroll_end = on_scroll_end
        self._on_button = on_button
        self._port = port
        self._server: Soup.Server | None = None
        self._code = ""
        self._token = ""
        self._idle_id: int | None = None
        self._last_seen = 0.0
        # When a request last arrived *bearing the token*. Separate from
        # `_last_seen`, which starts the idle clock at start(): a server
        # nobody has scanned yet must not claim a phone is connected.
        self._talked_at = 0.0
        self._wrong_attempts = 0
        self._locked = False
        # What the phone draws. Published from the home screen; serialised
        # only when a poll actually asks for a version it hasn't seen.
        self._feed = StateFeed()
        # Ids served in search results. `/launch` and `/art` accept these as
        # well as the ones in the published state — see core.remote for why
        # a result list is not published and why this is bounded.
        self._offered = OfferedIds()
        # Open EventSource connections. The 1 Hz poll is still there and
        # still correct; this is what makes a press feel immediate instead
        # of up to a second late, and the page falls back to polling on any
        # browser or proxy that will not hold the stream open.
        self._streams: list[Soup.ServerMessage] = []
        # Text goes wherever is currently asking for it, which is nowhere
        # most of the time. A sink rather than a constructor argument
        # because one server now serves several screens: search, each of the
        # tile editor's fields, and the remote, which asks for none.
        self._text_sink: Callable[[str], None] | None = None
        # Reference counted: the remote and an open text field can both want
        # the server, and whichever is dismissed first must not take the
        # port out from under the other.
        self._holders: set[str] = set()

    # --- who wants it running --------------------------------------------

    def acquire(self, holder: str) -> bool:
        """Start the server on behalf of `holder`, or note that it already
        wants it. Returns False only if starting actually failed."""
        self._holders.add(holder)
        return self.start()

    def release(self, holder: str) -> None:
        self._holders.discard(holder)
        if not self._holders:
            self.stop()

    def holds(self, holder: str) -> bool:
        return holder in self._holders

    def set_text_sink(self, sink: Callable[[str], None] | None) -> None:
        """Where typed text lands, or None when nothing on screen wants it."""
        self._text_sink = sink

    def release_text_sink(self, sink: Callable[[str], None]) -> None:
        """Give the sink back, but only if it is still ours.

        Screens hand the sink over as they appear and take it back as they
        go, and GTK maps the incoming one before it unmaps the outgoing —
        so an unconditional clear on the way out would leave the phone
        typing into nothing on the screen that just arrived.
        """
        if self._text_sink is sink:
            self._text_sink = None

    # --- what the phone sees ---------------------------------------------

    def publish(self, state: RemoteState) -> bool:
        """Offer a new snapshot to whatever phones are polling.

        Cheap enough to call from every focus move and every catalogue
        rebuild: an unchanged state costs one dataclass comparison, and even
        a changed one is not serialised until someone asks.

        A phone holding an event stream open counts as asking, so a real
        change is serialised once here and written to all of them. That is
        the whole difference between the stream and the poll: the poll
        cannot be told, it can only ask, and a second is a long time to
        wait to see that the button you pressed did something.
        """
        changed = self._feed.publish(state)
        if changed and self._streams:
            self._broadcast(self._feed.payload())
        return changed

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def code(self) -> str:
        return self._code

    @property
    def token(self) -> str:
        return self._token

    @property
    def locked(self) -> bool:
        """Too many wrong codes. The server keeps listening — refusing every
        request is the point — but nothing it is sent can be typed any
        more."""
        return self._locked

    @property
    def connected(self) -> bool:
        """Has an authenticated request arrived recently?

        There is no session to be connected *to* — the credential travels
        with each request — so "connected" is the only thing that can
        honestly be said: something with the token was talking to us a
        moment ago. The window is a little over the phone's one-second poll,
        so a phone with the page open reads as connected and one that has
        been closed stops doing so within a few seconds.
        """
        return self.running and (time.monotonic() - self._talked_at) < _CONNECTED_SECONDS

    @property
    def url(self) -> str | None:
        """The address to type in by hand. Pairs with the four-digit code."""
        address = local_address()
        return f"http://{address}:{self._port}" if address else None

    @property
    def pair_url(self) -> str | None:
        """The address to put in the QR code: the same page, carrying the
        session token in its fragment so that scanning it is the whole of
        connecting. See the module docstring on why the fragment."""
        base = self.url
        if base is None or not self._token:
            return None
        return f"{base}/#k={self._token}"

    # --- lifecycle -------------------------------------------------------

    def start(self) -> bool:
        if self._server is not None:
            return True
        self._code = f"{secrets.randbelow(10000):04d}"
        self._token = secrets.token_urlsafe(_TOKEN_BYTES)
        self._wrong_attempts = 0
        self._locked = False
        server = Soup.Server()
        server.add_handler("/", self._handle_page)
        server.add_handler("/manifest.webmanifest", self._handle_manifest)
        server.add_handler("/icon.svg", self._handle_icon)
        for clip_path in _AWAKE_CLIPS:
            server.add_handler(clip_path, self._handle_awake)
        server.add_handler("/connect", self._handle_connect)
        server.add_handler("/state", self._handle_state)
        server.add_handler("/events", self._handle_events)
        server.add_handler("/search", self._handle_search)
        server.add_handler("/tile", self._handle_tile_action)
        server.add_handler("/volume", self._handle_volume)
        server.add_handler("/art", self._handle_art)
        server.add_handler("/type", self._handle_type)
        server.add_handler("/action", self._handle_action)
        server.add_handler("/launch", self._handle_launch)
        server.add_handler("/transport", self._handle_transport)
        server.add_handler("/pointer", self._handle_pointer)
        try:
            server.listen_all(self._port, Soup.ServerListenOptions(0))
        except GLib.Error:
            return False
        self._server = server
        self._last_seen = time.monotonic()
        self._talked_at = 0.0
        self._idle_id = GLib.timeout_add_seconds(_IDLE_CHECK_SECONDS, self._check_idle)
        return True

    def stop(self) -> None:
        self._close_streams()
        self._offered.clear()
        if self._idle_id is not None:
            GLib.source_remove(self._idle_id)
            self._idle_id = None
        if self._server is not None:
            self._server.disconnect()
            self._server = None
        self._code = ""
        self._token = ""
        self._talked_at = 0.0
        self._wrong_attempts = 0
        self._locked = False
        self._holders.clear()

    def _check_idle(self) -> bool:
        # Someone is holding this open on purpose. A phone with its screen
        # off sends nothing — that is not the same as nobody wanting the
        # remote, and treating it as such is how the remote died mid-film.
        if self._holders:
            return GLib.SOURCE_CONTINUE
        if time.monotonic() - self._last_seen < SESSION_TIMEOUT_SECONDS:
            return GLib.SOURCE_CONTINUE
        self._idle_id = None
        self.stop()
        return GLib.SOURCE_REMOVE

    def _touch(self) -> None:
        """Push the idle deadline out. Called for every accepted request."""
        self._last_seen = self._talked_at = time.monotonic()

    # --- the gate --------------------------------------------------------

    def _from_local_network(self, message: Soup.ServerMessage) -> bool:
        """Refuse anything that did not come from our own network.

        A source we can't identify is refused too: the alternative is
        deciding that an unreadable address is trustworthy.
        """
        address = message.get_remote_address()
        if isinstance(address, Gio.InetSocketAddress):
            inet = address.get_address()
            return inet is not None and is_local_address(inet.to_string())
        return False

    @staticmethod
    def _refuse(message: Soup.ServerMessage, status: int, text: str) -> None:
        message.set_status(status, None)
        message.set_response("text/plain; charset=utf-8", Soup.MemoryUse.COPY, text.encode())

    def _fields(self, message: Soup.ServerMessage) -> dict[str, object] | None:
        """The JSON body of a POST, or None having written the refusal."""
        if message.get_method() != "POST":
            message.set_status(Soup.Status.METHOD_NOT_ALLOWED, None)
            return None
        body = message.get_request_body()
        payload = bytes(body.flatten().get_data() or b"")
        try:
            fields = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            fields = None
        if not isinstance(fields, dict):
            self._refuse(message, Soup.Status.BAD_REQUEST, "Malformed request.")
            return None
        return fields

    def _has_token(self, candidate: object) -> bool:
        # compare_digest even here, where the secret is long enough that a
        # timing oracle is not a practical route in: it costs nothing, and
        # the alternative is a reader having to work out why this one
        # comparison is different from the other.
        return bool(self._token) and secrets.compare_digest(str(candidate or ""), self._token)

    def _authorize(self, message: Soup.ServerMessage) -> dict[str, object] | None:
        """The gate every POST but `/connect` goes through. Returns the
        request's fields, or None having already written the refusal.

        One function rather than eight, because the D-pad, the trackpad, the
        catalogue and the launch endpoint must all be exactly as hard to
        reach as the keyboard was — an endpoint that skipped the credential
        would make the credential pointless.
        """
        if not self._from_local_network(message):
            self._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return None
        fields = self._fields(message)
        if fields is None:
            return None
        if self._locked:
            self._refuse(
                message,
                _STATUS_TOO_MANY_REQUESTS,
                "Too many wrong codes. Turn the phone remote off and on again on the TV.",
            )
            return None
        if not self._has_token(fields.get("key")):
            # 401, not 403: this is "your session is over", and the page
            # turns it into the code screen rather than an error.
            self._refuse(message, Soup.Status.UNAUTHORIZED, "Not connected any more.")
            return None
        self._touch()
        return fields

    def _authorize_get(
        self, message: Soup.ServerMessage, query: dict[str, str] | None
    ) -> bool:
        """The same gate for the two things a browser fetches by URL rather
        than by script: the state poll and a tile's artwork. An `<img>` tag
        cannot send a POST body, so the token travels in the query string —
        which is exactly why the token is what is in the QR and the code is
        not: a guessable secret in a URL is a guessable secret in a log.
        """
        if message.get_method() != "GET":
            message.set_status(Soup.Status.METHOD_NOT_ALLOWED, None)
            return False
        if not self._from_local_network(message):
            self._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return False
        if self._locked:
            self._refuse(message, _STATUS_TOO_MANY_REQUESTS, "Locked.")
            return False
        if not self._has_token((query or {}).get("k")):
            self._refuse(message, Soup.Status.UNAUTHORIZED, "Not connected any more.")
            return False
        self._touch()
        return True

    @staticmethod
    def _ok(message: Soup.ServerMessage) -> None:
        message.set_status(Soup.Status.OK, None)
        message.set_response("application/json", Soup.MemoryUse.COPY, b"{}")

    @staticmethod
    def _json(message: Soup.ServerMessage, payload: bytes) -> None:
        message.set_status(Soup.Status.OK, None)
        message.set_response("application/json; charset=utf-8", Soup.MemoryUse.COPY, payload)

    # --- static assets ---------------------------------------------------

    def _serve_resource(
        self, message: Soup.ServerMessage, name: str, content_type: str
    ) -> None:
        """The page and its two attachments.

        Not behind the credential, and deliberately so: the phone has to be
        able to load the page *before* it can authenticate, and a browser
        fetches a manifest and an icon on its own without passing anything
        the script holds. Nothing served here contains a secret — the token
        arrives in the fragment, which never reaches this process.
        """
        if message.get_method() != "GET":
            message.set_status(Soup.Status.METHOD_NOT_ALLOWED, None)
            return
        if not self._from_local_network(message):
            self._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return
        data = _resource_bytes(name)
        if data is None:
            self._refuse(
                message,
                Soup.Status.INTERNAL_SERVER_ERROR,
                "Salon could not find the remote's page. This copy may be installed wrong.",
            )
            return
        message.set_status(Soup.Status.OK, None)
        message.set_response(content_type, Soup.MemoryUse.COPY, data)

    def _handle_page(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        self._serve_resource(message, "index.html", "text/html; charset=utf-8")

    def _handle_manifest(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        self._serve_resource(message, "manifest.webmanifest", "application/manifest+json")

    def _handle_icon(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        self._serve_resource(message, "icon.svg", "image/svg+xml")

    def _handle_awake(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The clip that keeps the phone's screen on.

        `navigator.wakeLock` is gated on a secure context, and the remote is
        plain HTTP on a LAN address — so on a phone the API is not refused,
        it is *absent*, and the `"wakeLock" in navigator` guard around it
        made the whole feature dead code. Playing a muted video is the
        fallback every phone honours, and it needs something to play.
        """
        name, content_type = _AWAKE_CLIPS.get(path, ("", ""))
        if not name:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        self._serve_resource(message, name, content_type)

    # --- connecting ------------------------------------------------------

    def _handle_connect(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The one endpoint that accepts the four-digit code, and the only
        place wrong guesses are counted.

        Answers with the session token, which is what everything else
        wants. A phone that scanned the QR already has it and posts it back
        here anyway — that is how a stale code from a previous session ends
        up on the code screen instead of on a remote whose every button
        fails.
        """
        if not self._from_local_network(message):
            self._refuse(message, Soup.Status.FORBIDDEN, "Not on this network.")
            return
        fields = self._fields(message)
        if fields is None:
            return
        # Checked before the credential is even read: once a session is
        # burned it is burned for the right code too, so that guessing it on
        # the last allowed attempt wins nothing.
        if self._locked:
            self._refuse(
                message,
                _STATUS_TOO_MANY_REQUESTS,
                "Too many wrong codes. Turn the phone remote off and on again on the TV.",
            )
            return

        if self._has_token(fields.get("key")):
            self._touch()
            self._json(message, json.dumps({"key": self._token}).encode())
            return

        # compare_digest, not ==: the code is short enough that a timing
        # oracle is a real (if unglamorous) way to guess it.
        if not secrets.compare_digest(str(fields.get("code", "")), self._code):
            self._wrong_attempts += 1
            if self._wrong_attempts >= MAX_ATTEMPTS:
                self._locked = True
                if self._on_locked is not None:
                    GLib.idle_add(_notify, self._on_locked)
            self._refuse(message, Soup.Status.FORBIDDEN, "Wrong code.")
            return

        # A correct code proves whoever is holding the phone was told it, so
        # the earlier fumbles stop counting against them.
        self._wrong_attempts = 0
        self._touch()
        self._json(message, json.dumps({"key": self._token}).encode())

    # --- what is on the television ---------------------------------------

    def _handle_state(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The poll. Answers 204 when the phone is already current, which is
        most of the time — and matters because this handler runs on the same
        main loop that is animating the tiles."""
        if not self._authorize_get(message, query):
            return
        if self._feed.is_current((query or {}).get("v")):
            message.set_status(Soup.Status.NO_CONTENT, None)
            return
        self._json(message, self._feed.payload())

    def _handle_events(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """The state, pushed instead of polled.

        `text/event-stream`, held open, one `data:` line per real change.
        The poll is not removed and is not deprecated — it is the fallback,
        and it earns its place: a stream is a connection somebody's phone
        keeps open across a screen lock, a Wi-Fi roam and a browser tab
        eviction, and every one of those ends it silently. The page opens a
        stream, and if it ever closes or errors it goes back to asking once
        a second. Both paths read the same `StateFeed`, so they cannot
        disagree about what the television is showing.

        The body does not accumulate. Delivery works either way — measured,
        because the first version of this claimed otherwise — but with
        accumulation on, libsoup keeps every byte it has ever written to
        the response, and this is a response that is meant to live for as
        long as someone has the page open. That is a slow leak per connected
        phone rather than a broken feature, which is exactly the kind of
        thing that is invisible until a television has been on for a week.
        """
        if not self._authorize_get(message, query):
            return
        message.set_status(Soup.Status.OK, None)
        headers = message.get_response_headers()
        headers.set_content_type("text/event-stream", None)
        headers.append("Cache-Control", "no-cache")
        headers.append("Connection", "keep-alive")
        # Chrome and Safari both hold a stream in a buffer until enough
        # bytes arrive to bother with; a proxy in between will do the same.
        # Telling the browser to wait 2s before reconnecting, in a comment
        # line, doubles as the flush.
        headers.set_encoding(Soup.Encoding.EOF)
        body = message.get_response_body()
        body.set_accumulate(False)
        body.append(b": salon\nretry: 2000\n\n")
        # The current state immediately, so a phone that has just connected
        # draws the television rather than an empty page until something
        # over there happens to change.
        body.append(_sse_frame(self._feed.payload()))
        self._streams.append(message)
        message.connect("finished", self._on_stream_finished)

    def _on_stream_finished(self, message: Soup.ServerMessage) -> None:
        try:
            self._streams.remove(message)
        except ValueError:
            pass

    def _broadcast(self, payload: bytes) -> None:
        frame = _sse_frame(payload)
        for message in list(self._streams):
            try:
                message.get_response_body().append(frame)
                message.unpause()
            except (GLib.Error, TypeError):
                # A socket that has gone away between the "finished" signal
                # and now. Dropping it here rather than letting it throw on
                # every future publish.
                self._on_stream_finished(message)

    def _close_streams(self) -> None:
        for message in list(self._streams):
            try:
                message.get_response_body().complete()
                message.unpause()
            except (GLib.Error, TypeError):
                pass
        self._streams.clear()

    def _handle_search(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Search the catalogue and every installed application.

        The one thing the phone is unambiguously better at than the remote:
        the television's search screen is a keyboard drawn on a screen, and
        the device in your hand already has one. Results come back in the
        same shape the catalogue does, so they render with the same card,
        the same artwork endpoint and the same launch path.

        Answering synchronously is deliberate. Soup dispatches on the main
        loop, which is where the catalogue and the installed-app cache both
        live, so the handler can simply ask — no thread, no request id, no
        second round trip. The cost is that whatever fills `on_search` must
        stay cheap; see `HomeView._search_for_phone`, which ranks a list it
        already has rather than scanning the disk.
        """
        fields = self._authorize(message)
        if fields is None:
            return
        if self._on_search is None:
            self._refuse(message, Soup.Status.NOT_IMPLEMENTED, "Search isn't available.")
            return
        results = self._on_search(str(fields.get("q", "")))[:MAX_SEARCH_RESULTS]
        # Remembered before they are sent, so the /art request the page
        # makes for each result a moment later is answerable.
        self._offered.offer(tile.id for tile in results)
        self._json(
            message,
            json.dumps({"results": [tile.to_dict() for tile in results]}).encode(),
        )

    def _handle_tile_action(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Pin, unpin, edit or remove one tile — the phone's long-press.

        `Action.OPTIONS` has opened a per-tile menu on the television since
        the reachability pass, and the phone had no equivalent, so the one
        surface where every tile is visible at once was the one surface
        where none of them could be changed.

        The reply carries a sentence for the phone to show. These are the
        actions with a consequence that is not visible on the phone itself
        — "edit" opens a screen on the television, which is a strange thing
        to have happen with no acknowledgement in your hand.
        """
        fields = self._authorize(message)
        if fields is None:
            return
        tile_id = str(fields.get("id", ""))
        what = str(fields.get("what", ""))
        if self._on_tile_action is None or what not in TILE_ACTIONS:
            self._refuse(message, Soup.Status.BAD_REQUEST, "Unknown tile action.")
            return
        if not self._may_touch(tile_id):
            self._refuse(message, Soup.Status.NOT_FOUND, "That is not on the TV any more.")
            return
        self._json(message, json.dumps({"said": self._on_tile_action(tile_id, what)}).encode())

    def _handle_volume(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """An absolute level from the slider, or the mute toggle.

        Absolute, not a delta, because that is the whole reason the slider
        exists: two repeat-buttons already send VOLUME_UP and VOLUME_DOWN
        as ordinary Actions and will keep doing so. A finger dragged to a
        third of the way along is asking for a third of the way along, and
        expressing that as nineteen presses of a step key is how you get a
        volume control that lags behind the thumb moving it.
        """
        fields = self._authorize(message)
        if fields is None:
            return
        if fields.get("mute"):
            if self._on_mute is not None:
                mute = self._on_mute
                GLib.idle_add(_notify, mute)
            self._ok(message)
            return
        if self._on_volume is None:
            self._refuse(message, Soup.Status.NOT_IMPLEMENTED, "Volume isn't available.")
            return
        level = min(1.0, max(0.0, _finite(fields.get("level"))))
        callback = self._on_volume
        GLib.idle_add(lambda: _deliver_level(callback, level))
        self._ok(message)

    def _may_touch(self, tile_id: str) -> bool:
        """Whether the phone has been shown this tile.

        Two sources, one rule: the ids in the published state, and the ids
        served in a search result. Never the catalogue and never the
        filesystem — which is also why there is no path traversal to get
        wrong anywhere in this file.
        """
        return bool(tile_id) and (tile_id in self._feed.tile_ids() or tile_id in self._offered)

    def _handle_art(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """A tile's own image, straight off disk.

        The id is *matched against the published state*, never joined onto a
        path: the phone can ask for the artwork of something it was shown
        and for nothing else, so there is no traversal to get wrong.
        """
        if not self._authorize_get(message, query):
            return
        escaped = path.removeprefix("/art/") if path.startswith("/art/") else ""
        tile_id = GLib.uri_unescape_string(escaped, None) or "" if escaped else ""
        if not self._may_touch(tile_id) or self._art_for is None:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        art = self._art_for(tile_id)
        if art is None:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        try:
            if art.stat().st_size > _MAX_ART_BYTES:
                message.set_status(Soup.Status.NOT_FOUND, None)
                return
            data = art.read_bytes()
        except OSError:
            message.set_status(Soup.Status.NOT_FOUND, None)
            return
        message.set_status(Soup.Status.OK, None)
        # Immutable: the URL is keyed by tile id and the images behind it are
        # content the phone will scroll past repeatedly. A tile whose art
        # changes gets a new catalogue generation and a reload anyway.
        message.get_response_headers().append("Cache-Control", "private, max-age=3600")
        message.set_response(
            _ART_TYPES.get(art.suffix.lower(), "application/octet-stream"),
            Soup.MemoryUse.COPY,
            data,
        )

    # --- what the phone sends --------------------------------------------

    def _handle_type(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        fields = self._authorize(message)
        if fields is None:
            return
        text = str(fields.get("text", ""))
        sink = self._text_sink
        if sink is not None:
            GLib.idle_add(lambda: _deliver(sink, text))
            self._ok(message)
            return
        # Nothing in Salon wants this, which usually means a launched
        # application is in front. Type into *that* instead, through the
        # same RemoteDesktop grant the trackpad uses — a phone keyboard
        # that only works on Salon's own screens is a phone keyboard that
        # stops working exactly when a search box appears in Netflix.
        if self._on_remote_text is not None and self._on_remote_text(text):
            self._ok(message)
            return
        # Said plainly rather than swallowed: silence here looks exactly
        # like a broken connection.
        self._refuse(
            message,
            Soup.Status.CONFLICT,
            "Nothing on the TV is asking for text, and Salon isn't allowed "
            "to type into other apps. Turn on Settings \u2192 Input \u2192 "
            "Gamepad cursor to let it.",
        )

    def _handle_action(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        fields = self._authorize(message)
        if fields is None:
            return
        name = str(fields.get("action", ""))
        if self._on_action is None or name not in ACTION_NAMES:
            # An unknown name is a bad request, not a silent no-op: the page
            # and this set are edited in different places and drifting apart
            # would otherwise show up as buttons that do nothing.
            self._refuse(message, Soup.Status.BAD_REQUEST, "Unknown button.")
            return
        callback = self._on_action
        GLib.idle_add(lambda: _deliver(callback, name))
        self._ok(message)

    def _handle_launch(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Open a tile by id. Same launch path as a press on the television —
        the phone is not a second way in, it is a second remote."""
        fields = self._authorize(message)
        if fields is None:
            return
        tile_id = str(fields.get("id", ""))
        if self._on_launch is None or not self._may_touch(tile_id):
            self._refuse(message, Soup.Status.NOT_FOUND, "That is not on the TV any more.")
            return
        callback = self._on_launch
        GLib.idle_add(lambda: _deliver(callback, tile_id))
        self._ok(message)

    def _handle_transport(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        """Play/pause, next, previous — for the player the phone can see."""
        fields = self._authorize(message)
        if fields is None:
            return
        what = str(fields.get("what", ""))
        if self._on_transport is None or what not in TRANSPORT_NAMES:
            self._refuse(message, Soup.Status.BAD_REQUEST, "Unknown transport control.")
            return
        callback = self._on_transport
        GLib.idle_add(lambda: _deliver_transport(callback, what))
        self._ok(message)

    def _handle_pointer(
        self,
        server: Soup.Server,
        message: Soup.ServerMessage,
        path: str,
        query: dict[str, str] | None,
    ) -> None:
        fields = self._authorize(message)
        if fields is None:
            return
        if self._pointer_ready is not None and not self._pointer_ready():
            # The trackpad needs the desktop's RemoteDesktop grant, and
            # there are ordinary reasons not to have it — the permission was
            # declined, or the portal is still handshaking. A finger sliding
            # on a surface that answers 200 and moves nothing is the worst
            # of the available outcomes.
            self._refuse(
                message,
                Soup.Status.CONFLICT,
                "Salon isn't allowed to move the pointer. Turn on "
                "Settings \u2192 Input \u2192 Gamepad cursor, and allow the "
                "desktop's permission request.",
            )
            return
        # Ordered by how often each arrives, which is also the order the
        # gestures on the page fire in: motion during a drag, then the
        # scroll of a two-finger drag, then the once-per-gesture events.
        move = self._on_pointer
        if move is not None:
            dx = _finite(fields.get("dx"))
            dy = _finite(fields.get("dy"))
            if dx or dy:
                GLib.idle_add(lambda: _deliver_motion(move, dx, dy))
        scroll = self._on_scroll
        if scroll is not None:
            sx = _finite(fields.get("sx"))
            sy = _finite(fields.get("sy"))
            if sx or sy:
                GLib.idle_add(lambda: _deliver_motion(scroll, sx, sy))
        if fields.get("scrollEnd") and self._on_scroll_end is not None:
            finish = self._on_scroll_end
            GLib.idle_add(_notify, finish)
        # `button` names which one; a bare `click` stays "left" so an older
        # page — one a phone kept in its cache — goes on working.
        button = str(fields.get("button", "") or "left")
        if button not in POINTER_BUTTONS:
            self._refuse(message, Soup.Status.BAD_REQUEST, "Unknown mouse button.")
            return
        if fields.get("click"):
            if button == "left" and self._on_click is not None:
                click = self._on_click
                GLib.idle_add(_notify, click)
            elif self._on_button is not None:
                press = self._on_button
                GLib.idle_add(lambda: _deliver_button(press, button, "click"))
            self._ok(message)
            return
        # Press and release as separate events: this is what lets a
        # double-tap-and-drag on the phone move a window or select text,
        # which a tap that releases itself 50ms later can never do.
        held = str(fields.get("hold", ""))
        if held in ("down", "up") and self._on_button is not None:
            hold = self._on_button
            GLib.idle_add(lambda: _deliver_button(hold, button, held))
        self._ok(message)


def _finite(value: object) -> float:
    """A number from an untrusted JSON body, or zero.

    JSON permits NaN and Infinity in practice, and either of those reaching
    a pointer-motion accumulator moves the cursor somewhere it can never
    come back from.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0.0
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    # A phone screen is not a thousand pixels wide; anything larger is
    # either a bug or someone probing.
    return max(-2000.0, min(2000.0, number))


def _sse_frame(payload: bytes) -> bytes:
    """One server-sent event carrying the state JSON.

    The payload is JSON with no newlines in it (`json.dumps` with the
    separators `StateFeed` uses emits none, and a newline inside a `data:`
    line would split one event into two half-parsed ones), so this is a
    prefix and two line feeds rather than a line-by-line encoder.
    """
    return b"data: " + payload + b"\n\n"


def _deliver_button(callback: Callable[[str, str], None], button: str, what: str) -> bool:
    callback(button, what)
    return GLib.SOURCE_REMOVE


def _deliver_level(callback: Callable[[float], None], level: float) -> bool:
    callback(level)
    return GLib.SOURCE_REMOVE


def _deliver(callback: Callable[[str], None], text: str) -> bool:
    callback(text)
    return GLib.SOURCE_REMOVE


def _deliver_motion(callback: Callable[[float, float], None], dx: float, dy: float) -> bool:
    callback(dx, dy)
    return GLib.SOURCE_REMOVE


def _deliver_transport(callback: Callable[[str], bool], what: str) -> bool:
    callback(what)
    return GLib.SOURCE_REMOVE


def _notify(callback: Callable[[], None]) -> bool:
    callback()
    return GLib.SOURCE_REMOVE
