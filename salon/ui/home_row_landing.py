# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure rule for which tile a vertical move lands on.

Rows used to be dragged along by the cursor: every row was scrolled to the
one column the focus model carried, so walking right through a long row slid
the row *below* it sideways in lockstep — under a cursor that had never been
in it — until that row hit its own end clamp and stopped dead. Measured on a
1280px window with fourteen tiles above nine, the second row travelled 913px
and then jerked to a halt while the first kept going.

A row owns its own scroll offset instead, and nothing but the cursor being
*inside* it may move it. That leaves one question, which is this module: with
the rows at rest wherever they happen to be, which tile does UP or DOWN land
on? The answer is the one already under the cursor — nearest by screen
position, not by column index — so the ring travels straight up or down the
screen and no row moves at all.

In the ordinary case the two agree anyway: the focused tile of a row rests at
the safe-area margin (`_row_scroll_x`), so the tile under the cursor *is* the
column the destination row was left at, and the landing costs no motion at
all — measured, both rows unmoved to the pixel across eight presses.

They part company in one case: a row scrolled hard against its own end holds
its focused tile out to the right of the margin, so a press leaving it lands
a long way across the screen and the destination has to scroll to put that
tile back on the margin. Motion, then — but in the row that was just entered,
which is a row the eye is already on, rather than in one the cursor is merely
passing. That invariant is worth the scroll: the backdrop's pool of light and
every fade are placed from it, and abandoning it would move the lurch to the
*next* press instead, where a single RIGHT would jump the row by an arbitrary
fraction of a tile.
"""

from __future__ import annotations

import math


def landing_column(
    cursor_center: float,
    *,
    offset: float,
    bleed: float,
    step: float,
    width: float,
    count: int,
) -> int:
    """The column of `count` tiles whose card centre is nearest `cursor_center`.

    All x values are in the row viewport's coordinates, which span the
    window. `offset` is the row's scroll offset in tiles-box coordinates,
    where a card sits one `bleed` to the right of the box's own origin — the
    same convention `_row_scroll_x` uses.

    Rounds half away from zero rather than with `round()`, whose
    banker's rounding would send an exactly-between cursor to the even
    column and back again depending on which pair it fell between.
    """
    if count <= 0:
        return 0
    if step <= 0:
        return 0
    raw = (cursor_center - offset - bleed - width / 2.0) / step
    return max(0, min(count - 1, math.floor(raw + 0.5)))
