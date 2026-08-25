# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F401
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
from typing import Any

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
_STATUS_CONTENT_TOO_LARGE = 413
_MAX_REQUEST_BODY_BYTES = 64 * 1024

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


class PhoneRemoteComponent:
    """Hold the explicit owning server facade."""

    def __init__(self, owner: object) -> None:
        self._owner = owner


__all__ = [name for name in globals() if not name.startswith("__")]
