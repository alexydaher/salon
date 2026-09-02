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

import time
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
    # MPRIS reports both in microseconds. Position is a snapshot taken when
    # the properties were read; consumers advance it locally while playing.
    position_us: int = -1
    length_us: int = 0
    position_at: float = 0.0
    # `mpris:artUrl` exactly as the player published it, or "". Not resolved
    # here: this module is pure, and resolving it means either a filesystem
    # path or a decision to let a phone fetch someone else's CDN.
    art_url: str = ""

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

    def active_players(self) -> tuple[Player, ...]:
        """Every controllable player, in the order they were discovered.

        Discovery order and nothing else: pausing one source or starting
        another playing must not shuffle the cards on the phone's
        now-playing page, where each source carries its own transport
        controls and the one the play key targets is called out in place.
        A player keeps its slot from the moment it registers until it
        quits. Stopped players are deliberately absent: they have no
        transport state for a remote to control.
        """
        return tuple(player for player in self.players.values() if player.active)


def position_ms(player: Player, *, at: float | None = None) -> int:
    """Current timeline position from an MPRIS snapshot, ready for JSON."""
    if player.position_us < 0:
        return -1
    now = time.monotonic() if at is None else at
    elapsed_us = 0
    if player.status == PLAYING and player.position_at > 0:
        elapsed_us = max(0, round((now - player.position_at) * 1_000_000))
    position = player.position_us + elapsed_us
    if player.length_us > 0:
        position = min(position, player.length_us)
    return position // 1000


def describe(player: Player, *, include_status: bool = True) -> tuple[str, str]:
    """The two lines a now-playing surface shows.

    The title line is the track, not the application — "Blue Monday" is
    what the room wants to know; that it arrived via Firefox is not. The
    artist and application go on the second line. Surfaces with a separate
    state icon can omit the redundant status word.
    """
    title = player.title.strip() or player.identity or "Now playing"
    parts = [part for part in (player.artist.strip(), player.identity.strip()) if part]
    if include_status:
        state = "Playing" if player.status == PLAYING else "Paused"
        parts.insert(0, state)
    detail = " · ".join(parts)
    return title, detail
