# SPDX-License-Identifier: GPL-3.0-or-later
"""Which player is *the* player, and what to say about it. Pure — no gi.

A desktop session frequently has several MPRIS players registered at once:
a browser with a paused video in some background tab, a music player, and
whatever Salon itself launched. Picking the wrong one puts a tab nobody
remembers opening on the television and, worse, sends the remote's
play/pause to it.

The rules, in order:

1. Something actually playing beats everything. If two things are playing,
   the one that started playing most recently wins — that is the one the
   person in the room just chose.
2. Otherwise the most recently active paused player, so that pressing play
   resumes what was last watched rather than something from this morning.
3. Otherwise nothing, and the detail strip goes back to describing the
   cursor.

Kept out of `services/mpris.py` because it is the part with judgement in
it, and judgement is the part worth testing. The service does D-Bus.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PLAYING = "Playing"
PAUSED = "Paused"
STOPPED = "Stopped"


@dataclass(frozen=True, slots=True)
class Player:
    """One MPRIS player, reduced to what choosing between them needs."""

    bus_name: str
    identity: str
    status: str
    title: str = ""
    artist: str = ""
    # Monotonic seconds, set when this player was last seen to change. Not
    # a timestamp from the player: MPRIS has no such field, and the only
    # ordering available is the order Salon learned about the changes.
    changed_at: float = 0.0
    can_go_next: bool = False
    can_go_previous: bool = False

    @property
    def active(self) -> bool:
        return self.status in (PLAYING, PAUSED)


@dataclass(slots=True)
class Selection:
    players: dict[str, Player] = field(default_factory=dict)

    def update(self, player: Player) -> None:
        self.players[player.bus_name] = player

    def remove(self, bus_name: str) -> None:
        self.players.pop(bus_name, None)

    def current(self) -> Player | None:
        candidates = [p for p in self.players.values() if p.active]
        if not candidates:
            return None
        playing = [p for p in candidates if p.status == PLAYING]
        pool = playing or candidates
        # Most recently changed first; bus name only to make ties stable,
        # never as a preference for one application over another.
        return max(pool, key=lambda p: (p.changed_at, p.bus_name))


def describe(player: Player) -> tuple[str, str]:
    """The two lines the detail strip shows: what it is, and what is going
    on with it.

    The title line is the track, not the application — "Blue Monday" is
    what the room wants to know; that it arrived via Firefox is not. The
    application's name goes on the second line, where the state is, because
    that is where "is this the thing I think it is" gets answered.
    """
    title = player.title.strip() or player.identity or "Now playing"
    state = "Playing" if player.status == PLAYING else "Paused"
    parts = [part for part in (player.artist.strip(), player.identity.strip()) if part]
    detail = " · ".join([state, *parts])
    return title, detail
