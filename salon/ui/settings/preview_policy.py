# SPDX-License-Identifier: GPL-3.0-or-later
"""What a value list does to the screen behind it (pure, no gi).

Settings covers the home screen completely, so a row that changes how the
home screen *looks* is picked from a control of its own labels — "Tile size
70%", "Row density 85%" — which is not a claim anyone can evaluate. The
strip on `OPTIONS` was the first answer to that and it is still here; this
is the same answer wired to the press people actually make, which is OK.
"""

from __future__ import annotations

# What the strip along the bottom says while a list is open above it. OK
# and BACK are named because live preview writes the value as the cursor
# passes over it: without "BACK restores" printed somewhere, walking a list
# and leaving it would look exactly like having chosen the last thing
# touched.
PEEK_HINT = "LEFT/RIGHT previews  ·  OK keeps it  ·  BACK restores  ·  MENU goes home"


def previews_home(previewable: bool, has_choices: bool) -> bool:
    """Whether opening this row's list should collapse Settings and let the
    home screen render behind it.

    `previewable` is marked on the row where it is declared, rather than
    listed here, so a new visual setting opts in beside its own definition.
    The second half is the safety rail: collapsing the screen is only
    survivable while something is left to steer with, and on these rows
    that something is the list itself. A previewable row with no list would
    hide Settings and leave nothing on screen but a strip.
    """
    return previewable and has_choices


def choosing_hint(row_hint: str, previewable: bool) -> str:
    """The legend under a row, before its list is opened.

    A row whose list changes the screen behind it is doing something the
    others do not, and the legend is the only place that can say so — the
    press is the same OK either way.

    Terse because the line is finite and shared: the whole legend is four
    clauses ending in "MENU goes home", and the du scale means the number
    of characters that fit is the same on a 4K television as it is here.
    "over the home screen" spelled out pushed the way out of Settings off
    the end of the line.
    """
    return "OK opens the list over home" if previewable else row_hint
