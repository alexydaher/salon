# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure horizontal geometry for home-row navigation.

Rows used to be dragged along by the cursor: every row was scrolled to the
one column the focus model carried, so walking right through a long row slid
the row *below* it sideways in lockstep — under a cursor that had never been
in it — until that row hit its own end clamp and stopped dead. Measured on a
1280px window with fourteen tiles above nine, the second row travelled 913px
and then jerked to a halt while the first kept going.

A row owns its own scroll offset instead, and nothing but a horizontal move
that reaches its visible edge may move it. That leaves two questions, which
this module answers without GTK: which tile does UP or DOWN land on, and how
far does LEFT or RIGHT have to reveal a tile? Vertical movement picks the
nearest fully visible card and never moves the row. Horizontal movement keeps
the row still while the next card is visible, then reveals only the distance
that crossed the safe edge.

In the ordinary same-geometry case, rows at the same resting position have
their card centres aligned, so the tile under the cursor is immediate. Rows
with different geometry or resting positions use their actual screen-space
centres rather than pretending their column numbers line up.

The fully-visible qualification matters at a clipped edge: selecting a card
that is only peeking into the viewport would force the focus refresh to move
the row after the ring arrived. Restricting the landing candidates prevents
that two-stage motion by construction. If an unusually narrow viewport cannot
hold even one complete card, nearest-centre is the graceful fallback.
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
    viewport_width: float | None = None,
    safe_margin: float = 0.0,
) -> int:
    """The visible column whose card centre is nearest `cursor_center`.

    All x values are in the row viewport's coordinates, which span the
    window. `offset` is the row's scroll offset in tiles-box coordinates,
    where a card sits one `bleed` to the right of the box's own origin — the
    same convention `_row_scroll_x` uses.

    Rounds half away from zero rather than with `round()`, whose
    banker's rounding would send an exactly-between cursor to the even
    column and back again depending on which pair it fell between.
    """
    if count <= 0 or step <= 0:
        return 0
    raw = (cursor_center - offset - bleed - width / 2.0) / step
    nearest = max(0, min(count - 1, math.floor(raw + 0.5)))
    if viewport_width is None or viewport_width <= 0:
        return nearest

    # Inclusive indices of cards wholly inside the horizontal safe area.
    # A small tolerance keeps a card calculated onto an edge from being
    # rejected by floating-point noise after a resize or scale change.
    epsilon = 1e-7
    first = max(
        0,
        math.ceil((safe_margin - offset - bleed) / step - epsilon),
    )
    last = min(
        count - 1,
        math.floor(
            (viewport_width - safe_margin - offset - bleed - width) / step + epsilon
        ),
    )
    if first > last:
        return nearest
    return max(first, min(last, nearest))


def row_scroll_offset(
    position: float,
    *,
    viewport_width: float,
    safe_margin: float,
    bleed: float,
    step: float,
    content_width: float,
) -> float:
    """Translate offset for a row position measured in tile steps.

    Keeping the state in steps rather than pixels lets a scale or viewport
    change re-derive it with the new geometry. Both ends are clamped so a
    fitting row stays at the start and an overflowing row never exposes a
    void beyond its last card.
    """
    maximum = safe_margin - bleed
    minimum = min(
        maximum,
        viewport_width - safe_margin - bleed - max(0.0, content_width),
    )
    desired = maximum - max(0.0, position) * max(0.0, step)
    return max(minimum, min(maximum, desired))


def revealed_scroll_position(
    focused_column: int,
    current_position: float,
    *,
    viewport_width: float,
    safe_margin: float,
    bleed: float,
    step: float,
    width: float,
    content_width: float,
) -> float:
    """Keep a focused card visible with the least possible row movement."""
    if step <= 0 or content_width <= 0:
        return 0.0

    current_offset = row_scroll_offset(
        current_position,
        viewport_width=viewport_width,
        safe_margin=safe_margin,
        bleed=bleed,
        step=step,
        content_width=content_width,
    )
    card_left = current_offset + bleed + max(0, focused_column) * step
    first_left = safe_margin
    last_left = viewport_width - safe_margin - width
    if last_left < first_left:
        # The card cannot fit inside both margins. Centre it instead of
        # oscillating between two impossible edge constraints.
        wanted_left = (viewport_width - width) / 2.0
    else:
        wanted_left = max(first_left, min(last_left, card_left))

    wanted_offset = current_offset + wanted_left - card_left
    maximum = safe_margin - bleed
    minimum = min(
        maximum,
        viewport_width - safe_margin - bleed - content_width,
    )
    wanted_offset = max(minimum, min(maximum, wanted_offset))
    return max(0.0, (maximum - wanted_offset) / step)
