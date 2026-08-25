# SPDX-License-Identifier: GPL-3.0-or-later
"""What the phone is allowed to know about the television. Pure — no gi.

`services/pairing.py` grew from a keyboard into a remote, and a remote that
can only *send* is a remote you have to look up at the screen to use. This
is the other direction: the state the phone renders, and the rules about
who may ask for it.

Three things live here rather than in the service, and all three are here
because they are the parts with judgement in them:

**The shape of the payload.** `RemoteState` is a snapshot of everything the
phone draws — the rows, what is playing, where the cursor is. It is a plain
frozen dataclass so a test can assert on it without a display, an HTTP
client or a running GLib loop.

**When the payload changes.** `StateFeed` holds the current snapshot and a
version number that only moves when the snapshot actually differs. The
phone polls with the version it last saw and is told "unchanged" for free
most of the time — which matters more than it sounds, because `Soup.Server`
dispatches on the main loop, so every byte serialised for the phone is
serialised on the thread that is animating the tiles. Serialisation is
lazy: a state that is published and superseded before anyone asks for it is
never turned into JSON at all.

**Who may connect.** `is_local_address` is the trust boundary. The remote
is plaintext HTTP by design (see the module docstring in `pairing.py`), and
that trade is only defensible while "on the same network" is a meaningful
statement — so a request whose source is not a private, link-local or
loopback address is refused before the credential is even looked at. On a
machine with one Wi-Fi interface this changes nothing; on a dual-homed one,
or a host that ends up with a public address it did not expect, it is the
difference between a remote and an open door.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RemoteTile:
    """One tile, reduced to what a phone can draw.

    `has_art` rather than a URL: the image is fetched from `/art/<id>` and
    the phone needs to know whether to ask at all, because the fallback —
    the tile's accent as a flat card, exactly as the television draws a
    level-4 tile — is better than a broken image.
    """

    id: str
    title: str
    subtitle: str | None = None
    accent: str = "#3B4252"
    has_art: bool = False
    # How to place that image: "cover" for a still or a poster, which fills
    # the card, and "contain" for an application icon, which is drawn small
    # and centred on the accent. The television makes exactly this
    # distinction (services/artwork.py's `icon_texture` is separate from
    # `texture` for the same reason) and a phone that ignored it would show
    # a wall of 64px icons stretched across 16:9 cards.
    fit: str = "cover"
    # Whether this is in `favourite-tile-ids`, and whether it is a tile in
    # `tiles.json` that could be deleted. Both are here so the phone's
    # per-tile menu can offer the right verb — "Unpin" for something already
    # pinned, no "Remove" at all for a provider's row, which the phone
    # cannot edit because nothing in `tiles.json` describes it.
    pinned: bool = False
    removable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "accent": self.accent,
            "art": self.has_art,
            "fit": self.fit,
            "pinned": self.pinned,
            "removable": self.removable,
        }


@dataclass(frozen=True, slots=True)
class RemoteRow:
    id: str
    title: str | None
    tiles: tuple[RemoteTile, ...] = ()
    aspect: str = "wide"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "aspect": self.aspect,
            "tiles": [tile.to_dict() for tile in self.tiles],
        }


@dataclass(frozen=True, slots=True)
class RemoteNowPlaying:
    """Enough to draw a transport card. Deliberately not a position or a
    duration: MPRIS reports those as a value that has to be extrapolated
    against a clock, and a progress bar that has to be right to the frame
    is not worth a poll every second."""

    title: str
    detail: str
    playing: bool
    can_next: bool = False
    can_previous: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "detail": self.detail,
            "playing": self.playing,
            "next": self.can_next,
            "previous": self.can_previous,
        }


@dataclass(frozen=True, slots=True)
class RemoteState:
    """Everything the phone renders, as of one moment.

    Frozen and compared by value, which is what lets `StateFeed` decide
    whether anything actually changed without anyone having to remember to
    say so at each of the dozen call sites that publish.
    """

    rows: tuple[RemoteRow, ...] = ()
    now_playing: RemoteNowPlaying | None = None
    # Where the cursor is, so the phone can show it in its own grid rather
    # than making you look up at the television to find out.
    focus: tuple[int, int] | None = None
    # Which screen is in front: home, search, apps, settings, or the name
    # of a launched application. The phone uses it to label its Back button
    # honestly and to know when the television is busy.
    screen: str = "home"
    # A text field on the television is asking for input right now, so the
    # phone can open its keyboard without being told to.
    wants_text: bool = False
    # Salon holds the desktop's input grant, so the trackpad and the phone
    # keyboard reach *other* applications and not just Salon's own screens.
    # The phone says so rather than offering a pad that silently does
    # nothing over a launched browser.
    remote_input: bool = False
    # The user's own repeat cadence (§6.2), so held D-pad buttons on the
    # phone accelerate exactly like the ones on a controller instead of at
    # some second, hardcoded speed.
    repeat_delay_ms: int = 400
    repeat_interval_ms: int = 120
    # The interface accent the user chose in Settings → Appearance. The
    # phone is a second screen of the same launcher and should not be the
    # one surface that ignores the theme.
    accent: str = "#E8A33D"
    # The title of the application currently covering the television, or ""
    # for none. `screen` already carries the same name, but as one string
    # among six reserved words — the page cannot tell "an app called
    # Settings is in front" from "the Settings screen is open" without
    # this, and it now reshapes itself completely on the answer. Half the
    # buttons on the remote do nothing while an app is up, and a remote that
    # does not say which half is a remote you learn by failing.
    app: str = ""
    # 0..1, or -1 when the sink could not be read. The phone draws a slider
    # rather than two repeat-buttons: volume is the one control guaranteed
    # to work from behind any application, and it is the one a touchscreen
    # is unambiguously better at than a physical remote.
    volume: float = -1.0
    muted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [row.to_dict() for row in self.rows],
            "app": self.app,
            "volume": self.volume,
            "muted": self.muted,
            "playing": self.now_playing.to_dict() if self.now_playing else None,
            "focus": list(self.focus) if self.focus else None,
            "screen": self.screen,
            "wantsText": self.wants_text,
            "remoteInput": self.remote_input,
            "accent": self.accent,
            "repeat": {
                "delay": self.repeat_delay_ms,
                "interval": self.repeat_interval_ms,
            },
        }


@dataclass(slots=True)
class StateFeed:
    """The current state, its version, and the JSON for it — computed once.

    The version starts at 1 so that a phone which has seen nothing can send
    0 and be certain of getting a body back.
    """

    state: RemoteState = field(default_factory=RemoteState)
    version: int = 1
    _payload: bytes | None = field(default=None, repr=False)

    def publish(self, state: RemoteState) -> bool:
        """Record `state`. Returns whether it was actually different.

        Callers publish liberally — on every focus move, every catalogue
        rebuild, every MPRIS property change — and this is what keeps that
        from costing anything. Nothing is serialised here.
        """
        if state == self.state:
            return False
        self.state = state
        self.version += 1
        self._payload = None
        return True

    def payload(self) -> bytes:
        """The JSON body for the current state, built at most once per
        change no matter how many phones ask for it."""
        if self._payload is None:
            body = self.state.to_dict()
            body["v"] = self.version
            self._payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        return self._payload

    def is_current(self, version: str | int | None) -> bool:
        """Whether a polling phone is already up to date.

        Tolerant of whatever arrives in a query string, because this is
        reached from the network: anything unparseable means "I have
        nothing", which costs one extra body and never a traceback.
        """
        try:
            return int(version) == self.version  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False

    def tile_ids(self) -> frozenset[str]:
        """Every tile id the phone has been shown, which is exactly the set
        it is allowed to launch or ask for artwork for. A launch request
        naming anything else is refused rather than looked up: the phone
        cannot be a way to reach something that isn't on the screen."""
        return frozenset(tile.id for row in self.state.rows for tile in row.tiles)


@dataclass(slots=True)
class OfferedIds:
    """Every tile id the phone has been handed outside the state snapshot.

    `/launch` and `/art` answer only for things the phone was shown, and
    until search existed the published state was the whole of that set. It
    is not any more: a search result is a tile the phone has been given and
    can reasonably tap, and it is deliberately *not* in the snapshot —
    putting a transient result list into the state the television publishes
    would bump the version for every keystroke on somebody's phone.

    So results are recorded here as they are served, and the check becomes
    "shown to the phone" rather than "currently on the television". The set
    is bounded because it is fed from a network endpoint: without a cap, a
    phone typing letters at a large application list is a memory leak with
    a user interface. Oldest ids fall out first, which is the right end —
    a result from forty searches ago is not one anybody is still tapping.
    """

    limit: int = 400
    _ids: dict[str, None] = field(default_factory=dict, repr=False)

    def offer(self, ids: Iterable[str]) -> None:
        for item_id in ids:
            # Re-inserting moves it to the end, so an id that keeps coming
            # back in results keeps its place instead of ageing out.
            self._ids.pop(item_id, None)
            self._ids[item_id] = None
        while len(self._ids) > self.limit:
            self._ids.pop(next(iter(self._ids)))

    def __contains__(self, item_id: object) -> bool:
        return item_id in self._ids

    def clear(self) -> None:
        self._ids.clear()


# Written out rather than deferred to `ipaddress.is_private`, which does not
# mean what its name suggests: it is "not globally reachable", so it counts
# the documentation ranges (203.0.113.0/24 and friends) as private while
# leaving out RFC 6598 carrier-grade NAT — which some ISP-supplied routers
# really do hand to the devices on their own LAN. An explicit list says what
# is meant and does not shift under a Python upgrade.
_LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "127.0.0.0/8",  # loopback
        "10.0.0.0/8",  # RFC 1918
        "172.16.0.0/12",  # RFC 1918
        "192.168.0.0/16",  # RFC 1918
        "100.64.0.0/10",  # RFC 6598, carrier-grade NAT
        "169.254.0.0/16",  # link-local
        "::1/128",  # loopback
        "fe80::/10",  # link-local
        "fc00::/7",  # unique local
    )
)


def is_local_address(text: str) -> bool:
    """Is this source address one on our own network?

    IPv4-mapped IPv6 sources are unwrapped first, because a dual-stack
    listener reports a LAN client as `::ffff:192.168.1.4`, and treating that
    as "some IPv6 address I don't recognise" would refuse the phone on most
    home routers. A zone index (`fe80::1%wlan0`) is stripped for the same
    reason: it is how a link-local source always arrives.
    """
    try:
        address = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(address in network for network in _LOCAL_NETWORKS)
