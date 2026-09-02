# SPDX-License-Identifier: GPL-3.0-or-later
"""Choosing between MPRIS players (salon/core/nowplaying.py).

A session usually has more than one: a browser holding a paused video in a
tab nobody remembers opening, a music player, and whatever Salon launched.
Choosing wrong does not look like a bug — it looks like the remote's
play/pause key being broken, because it went to the wrong player.
"""

from __future__ import annotations

from salon.core.nowplaying import PAUSED, PLAYING, STOPPED, Player, Selection, describe, position_ms


def _player(name: str, status: str, at: float, **kwargs: object) -> Player:
    return Player(bus_name=f"org.mpris.MediaPlayer2.{name}", identity=name.title(),
                  status=status, changed_at=at, **kwargs)  # type: ignore[arg-type]


def test_nothing_registered_is_nothing_playing() -> None:
    assert Selection().current() is None


def test_a_playing_player_beats_a_more_recent_paused_one() -> None:
    """The paused browser tab must never win over the film on screen."""
    selection = Selection()
    selection.update(_player("vlc", PLAYING, at=1.0))
    selection.update(_player("firefox", PAUSED, at=99.0))
    current = selection.current()
    assert current is not None and current.identity == "Vlc"


def test_the_most_recent_of_two_playing_wins() -> None:
    """Two things playing at once is a mistake in progress; the remote
    should reach the one the person just started."""
    selection = Selection()
    selection.update(_player("spotify", PLAYING, at=10.0))
    selection.update(_player("mpv", PLAYING, at=20.0))
    current = selection.current()
    assert current is not None and current.identity == "Mpv"


def test_the_most_recent_paused_wins_when_nothing_plays() -> None:
    selection = Selection()
    selection.update(_player("firefox", PAUSED, at=5.0))
    selection.update(_player("spotify", PAUSED, at=6.0))
    current = selection.current()
    assert current is not None and current.identity == "Spotify"


def test_stopped_players_are_not_candidates() -> None:
    """A stopped player is one that finished. Offering to resume it puts
    something nobody asked for on the strip."""
    selection = Selection()
    selection.update(_player("vlc", STOPPED, at=100.0))
    assert selection.current() is None


def test_every_active_player_is_available_for_independent_controls() -> None:
    selection = Selection()
    selection.update(_player("spotify", PLAYING, at=10.0))
    selection.update(_player("youtube", PAUSED, at=20.0))
    selection.update(_player("firefox", PLAYING, at=30.0))
    selection.update(_player("vlc", STOPPED, at=40.0))

    players = selection.active_players()
    assert [player.identity for player in players] == ["Spotify", "Youtube", "Firefox"]
    assert all(player.status != STOPPED for player in players)


def test_active_players_keep_their_slot_across_play_pause() -> None:
    """The phone's now-playing page draws one card per source; toggling
    play/pause on any of them must not reshuffle the list."""
    selection = Selection()
    selection.update(_player("spotify", PLAYING, at=10.0))
    selection.update(_player("firefox", PAUSED, at=20.0))
    selection.update(_player("mpv", PLAYING, at=30.0))
    before = [player.bus_name for player in selection.active_players()]

    selection.update(_player("spotify", PAUSED, at=40.0))
    selection.update(_player("firefox", PLAYING, at=50.0))
    after = [player.bus_name for player in selection.active_players()]

    assert before == after


def test_a_player_that_quits_stops_being_current() -> None:
    """A closed browser sends no further properties, so without removal it
    would sit on the strip for ever."""
    selection = Selection()
    selection.update(_player("firefox", PLAYING, at=1.0))
    selection.remove("org.mpris.MediaPlayer2.firefox")
    assert selection.current() is None


def test_the_track_leads_and_the_application_follows() -> None:
    """What the room wants to know is the track. That it arrived via
    Firefox belongs on the second line, next to the state."""
    title, detail = describe(
        _player("firefox", PLAYING, at=1.0, title="Blue Monday", artist="New Order")
    )
    assert title == "Blue Monday"
    assert detail == "Playing · New Order · Firefox"


def test_a_player_with_no_track_still_says_something_true() -> None:
    title, detail = describe(_player("mpv", PAUSED, at=1.0))
    assert title == "Mpv"
    assert detail == "Paused · Mpv"


def test_status_can_be_left_to_the_home_screen_icon() -> None:
    title, detail = describe(
        _player("firefox", PLAYING, at=1.0, title="Blue Monday", artist="New Order"),
        include_status=False,
    )
    assert title == "Blue Monday"
    assert detail == "New Order · Firefox"


def test_playing_position_advances_from_the_snapshot_and_stops_at_the_end() -> None:
    player = _player(
        "spotify", PLAYING, at=1.0, position_us=107_000_000,
        length_us=112_000_000, position_at=50.0,
    )
    assert position_ms(player, at=53.0) == 110_000
    assert position_ms(player, at=60.0) == 112_000
