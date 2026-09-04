# SPDX-License-Identifier: GPL-3.0-or-later
"""What the console rail's now-playing card shows, and where its cursor is.

**The card draws exactly one media source.** It used to stack them — the
first one properly, the rest as single lines, as many of those as the
rail's leftover height allowed — which made the card's whole shape a
function of two things nobody chose: how many MPRIS players happened to be
registered, and whether the pairing card was standing at the bottom of the
same rail. The same television therefore drew two different cards depending
on whether a phone had been paired, and the second, compressed arrangement
existed only to survive the first one's growth.

One source at a time instead, with a pair of arrows beside the heading, and
every source reachable through them. That fixes the card's height by
construction, which is what lets the design be the same with the QR card
standing under it and without it.

Everything here is pure: which source is showing, what the picker says, and
where the D-pad's cursor is among the card's keys.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from salon.core.actions import Action

HEADING = "NOW PLAYING"


def source_position(index: int, count: int) -> str:
    """"2/3", or nothing at all while there is only one source.

    The heading used to carry the count ("NOW PLAYING · 3"), which said how
    many sources there were without saying which of them was on screen.
    With a picker beside it, the pair of numbers answers both questions in
    the space the count alone used to take.
    """
    if count <= 1:
        return ""
    return f"{min(max(index, 0), count - 1) + 1}/{count}"


def step_source(index: int, count: int, *, forward: bool) -> int:
    """The source after or before `index`, wrapping.

    Wrapping rather than clamping: each arrow is a D-pad stop of its own,
    and a key that stops doing anything at the end of a list whose extent
    nobody can see reads as broken from three metres away.
    """
    if count <= 0:
        return 0
    return (index + (1 if forward else -1)) % count


def select_source(sources: Sequence[str], showing: str, fallback: str) -> int:
    """Which source the card should be on after a fresh MPRIS snapshot.

    The one it was already showing, wherever that has moved to in the list;
    failing that whatever the watcher calls current; failing that the
    first. A snapshot arrives on every position update and on every player
    coming or going, so following the *name* is what keeps a chosen source
    from sliding out from under the picker while a film is watched.
    """
    for candidate in (showing, fallback):
        if candidate:
            for index, source in enumerate(sources):
                if source == candidate:
                    return index
    return 0


class CardKey(StrEnum):
    """Every control on the card. `card_rows` says where each one sits."""

    PREVIOUS_SOURCE = "previous_source"
    NEXT_SOURCE = "next_source"
    PREVIOUS_TRACK = "previous_track"
    PLAY_PAUSE = "play_pause"
    NEXT_TRACK = "next_track"


# What the detail strip says while the cursor rests on each key. The rail is
# reached by a press nobody was told about, so the strip is the only thing
# that can explain what the ring has just landed on.
KEY_HINTS: dict[CardKey, tuple[str, str]] = {
    CardKey.PREVIOUS_SOURCE: ("Previous source", "Show the media source before this one"),
    CardKey.NEXT_SOURCE: ("Next source", "Show the next media source"),
    CardKey.PREVIOUS_TRACK: ("Previous track", "Go back in what is playing"),
    CardKey.PLAY_PAUSE: ("Play or pause", "Toggle the source on the card"),
    CardKey.NEXT_TRACK: ("Next track", "Skip forward in what is playing"),
}

_PICKER = (CardKey.PREVIOUS_SOURCE, CardKey.NEXT_SOURCE)
_TRANSPORT = (CardKey.PREVIOUS_TRACK, CardKey.PLAY_PAUSE, CardKey.NEXT_TRACK)

CardLayout = tuple[tuple[CardKey, ...], ...]


def card_rows(sources: int) -> CardLayout:
    """The card's D-pad stops, row by row.

    The picker exists only while there is a second source to pick: two
    arrows over a lone player are two keys that do nothing, and they would
    still cost a press each on the way to the transport.
    """
    return (_PICKER, _TRANSPORT) if sources > 1 else (_TRANSPORT,)


@dataclass(frozen=True, slots=True)
class CardCursor:
    row: int = 0
    col: int = 0


def clamp_cursor(rows: CardLayout, cursor: CardCursor) -> CardCursor:
    """The nearest real stop to `cursor`.

    The picker row appears and disappears with the second source, so a
    cursor held across a snapshot can name a row that no longer exists.
    """
    if not rows:
        return CardCursor(0, 0)
    row = min(max(cursor.row, 0), len(rows) - 1)
    return CardCursor(row, min(max(cursor.col, 0), len(rows[row]) - 1))


def key_at(rows: CardLayout, cursor: CardCursor) -> CardKey | None:
    if not rows:
        return None
    here = clamp_cursor(rows, cursor)
    return rows[here.row][here.col]


def entry_cursor(rows: CardLayout) -> CardCursor:
    """Where the cursor lands on the way in from the tiles.

    The play key rather than the stop nearest the tiles: pausing is what a
    press into the card is overwhelmingly for, so landing on it makes the
    common case one press in and one press to act.
    """
    for index, row in enumerate(rows):
        if CardKey.PLAY_PAUSE in row:
            return CardCursor(index, row.index(CardKey.PLAY_PAUSE))
    return CardCursor(0, 0)


def move_cursor(rows: CardLayout, cursor: CardCursor, action: Action) -> CardCursor | None:
    """Where a direction press puts the card's cursor.

    `None` is the press leaving the card altogether, and RIGHT off the end
    of a row is the only press that does it: the rail is the screen's left
    edge, so the way out is the way back to the tiles. Every other edge
    holds. There is nothing above the card in the rail and nothing below it
    but the pairing card, and a press that quietly jumped elsewhere would
    strand the arrows, which have exactly one route in.
    """
    if not rows:
        return None
    here = clamp_cursor(rows, cursor)
    if action is Action.RIGHT:
        if here.col + 1 >= len(rows[here.row]):
            return None
        return CardCursor(here.row, here.col + 1)
    if action is Action.LEFT:
        return CardCursor(here.row, max(0, here.col - 1))
    if action is Action.UP or action is Action.DOWN:
        row = here.row + (-1 if action is Action.UP else 1)
        if not (0 <= row < len(rows)):
            return here
        return clamp_cursor(rows, CardCursor(row, here.col))
    return here
