# SPDX-License-Identifier: GPL-3.0-or-later
"""The phone's view of the television: what changes, and who may look.

`core/remote.py` is pure, so all of this runs headlessly — which is the
point of it being pure. Two things are worth pinning down here rather than
over HTTP: that a snapshot which has not changed does not count as a change
(the phone polls once a second on the main loop, and the cost of getting
that wrong is dropped frames on the television), and that the trust boundary
knows a LAN address from a public one.
"""

from __future__ import annotations

import json

from salon.core.remote import (
    RemoteNowPlaying,
    RemoteRow,
    RemoteState,
    RemoteTile,
    StateFeed,
    is_local_address,
)


def _state(**kwargs) -> RemoteState:
    base = {
        "rows": (
            RemoteRow(
                id="streaming",
                title="Streaming",
                tiles=(RemoteTile(id="netflix", title="Netflix", has_art=True),),
            ),
        ),
    }
    return RemoteState(**{**base, **kwargs})


# --- the feed -------------------------------------------------------------


def test_republishing_the_same_state_is_not_a_change() -> None:
    """The whole reason every caller can publish liberally. `_update_focus`
    runs on every cursor move; if an identical snapshot bumped the version,
    the phone would re-download the catalogue for nothing."""
    feed = StateFeed()
    assert feed.publish(_state())
    version = feed.version
    assert not feed.publish(_state())
    assert feed.version == version


def test_a_real_change_bumps_the_version() -> None:
    feed = StateFeed()
    feed.publish(_state())
    before = feed.version
    assert feed.publish(_state(screen="settings"))
    assert feed.version == before + 1


def test_the_payload_is_built_once_and_reused() -> None:
    """Serialisation happens on the same main loop that animates the tiles,
    so two phones — or one polling twice — must not cost two dumps."""
    feed = StateFeed()
    feed.publish(_state())
    first = feed.payload()
    assert feed.payload() is first


def test_a_change_invalidates_the_payload() -> None:
    feed = StateFeed()
    feed.publish(_state())
    feed.payload()
    feed.publish(_state(screen="search"))
    assert json.loads(feed.payload())["screen"] == "search"


def test_a_state_that_was_superseded_before_anyone_asked_is_never_serialised() -> None:
    """Lazy, not eager: publishing is cheap enough to do from a dozen call
    sites precisely because nothing is turned into JSON until a poll
    arrives."""
    feed = StateFeed()
    feed.publish(_state(screen="home"))
    feed.publish(_state(screen="search"))
    feed.publish(_state(screen="settings"))
    assert json.loads(feed.payload())["screen"] == "settings"


def test_a_phone_that_has_seen_nothing_always_gets_a_body() -> None:
    """The version starts at 1 so that `v=0` — what the page sends before
    its first answer — can never accidentally match."""
    feed = StateFeed()
    assert not feed.is_current("0")
    assert not feed.is_current(0)


def test_an_unparseable_version_means_out_of_date() -> None:
    """This value comes off the network. Anything that is not a number is
    "I have nothing", which costs one extra body and never a traceback."""
    feed = StateFeed()
    for junk in (None, "", "NaN", "twelve", "1; DROP TABLE"):
        assert not feed.is_current(junk)


def test_the_current_version_is_recognised() -> None:
    feed = StateFeed()
    feed.publish(_state())
    assert feed.is_current(str(feed.version))
    assert feed.is_current(feed.version)


def test_the_launchable_set_is_exactly_what_was_published() -> None:
    """`/launch` and `/art` are checked against this. A tile that has left
    the catalogue must stop being reachable when the snapshot says so, not
    when someone remembers to clear a cache."""
    feed = StateFeed()
    feed.publish(_state())
    assert feed.tile_ids() == frozenset({"netflix"})
    feed.publish(RemoteState())
    assert feed.tile_ids() == frozenset()


def test_the_payload_carries_everything_the_page_draws() -> None:
    feed = StateFeed()
    feed.publish(
        _state(
            now_playing=RemoteNowPlaying(
                title="Blue Monday", detail="Playing · New Order", playing=True, can_next=True
            ),
            focus=(0, 0),
            screen="home",
            wants_text=True,
            accent="#E8A33D",
        )
    )
    body = json.loads(feed.payload())
    assert body["v"] == feed.version
    assert body["focus"] == [0, 0]
    assert body["wantsText"] is True
    assert body["remoteInput"] is False
    assert body["accent"] == "#E8A33D"
    assert body["playing"]["title"] == "Blue Monday"
    assert body["playing"]["next"] is True
    assert body["playing"]["previous"] is False
    assert body["rows"][0]["tiles"][0] == {
        "id": "netflix",
        "title": "Netflix",
        "subtitle": None,
        "accent": "#3B4252",
        "art": True,
        "fit": "cover",
    }


# --- the trust boundary ---------------------------------------------------


def test_addresses_on_our_own_network_are_allowed() -> None:
    for address in (
        "127.0.0.1",
        "10.0.0.5",
        "172.16.4.1",
        "172.31.255.254",
        "192.168.1.151",
        "100.64.0.1",  # RFC 6598, carrier-grade NAT
        "169.254.3.4",  # link-local
        "::1",
        "fe80::1",
        "fd00::1234",  # unique local
    ):
        assert is_local_address(address), address


def test_public_addresses_are_refused() -> None:
    """The remote is plaintext HTTP by design, and that is only defensible
    while "on the same network" means something."""
    for address in ("8.8.8.8", "1.1.1.1", "172.32.0.1", "203.0.113.9", "2001:4860:4860::8888"):
        assert not is_local_address(address), address


def test_an_ipv4_mapped_source_is_unwrapped_before_it_is_judged() -> None:
    """A dual-stack listener reports a LAN phone as `::ffff:192.168.1.4`.
    Treating that as an unrecognised IPv6 address would refuse the phone on
    most home routers."""
    assert is_local_address("::ffff:192.168.1.4")
    assert not is_local_address("::ffff:8.8.8.8")


def test_a_zone_index_does_not_confuse_the_check() -> None:
    """Link-local IPv6 arrives with the interface appended."""
    assert is_local_address("fe80::1ff:fe23:4567:890a%wlan0")


def test_something_that_is_not_an_address_is_refused() -> None:
    """A source we cannot identify is refused, rather than the alternative:
    deciding that an unreadable address is trustworthy."""
    for junk in ("", "localhost", "not an address", "192.168.1"):
        assert not is_local_address(junk), junk
