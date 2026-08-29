# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the cursor starts, and how far the list scrolls. Pure.

Split out of `settings_list.py` because these are the two decisions in that
file worth testing on their own, and neither needs a widget to make —
`tests/test_settings_rows.py` drives them directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from salon.ui.settings.settings_row import SettingsRow


def _first_stop(rows: list[SettingsRow]) -> int:
    """The first *actionable* row, not merely the first selectable one.

    About and Audio both led with a read-only fact, so opening either
    announced itself with "Nothing to change on this row". Read-only rows
    stay reachable with UP.
    """
    return next(
        (index for index, row in enumerate(rows) if row.actionable),
        next((index for index, row in enumerate(rows) if row.selectable), 0),
    )


def _rebuilt_selection(
    keys: Sequence[str],
    selectable: Sequence[bool],
    *,
    previous_key: str,
    previous_index: int,
    pinned: bool,
) -> int | None:
    """Where the cursor goes when a panel rebuilds under it.

    ``None`` means "wherever `_first_stop` says", which is the answer in
    the case this exists for: a panel whose rows arrive *after* it opened.
    Audio asks wpctl for the outputs on a worker thread, so the first build
    is `No outputs found` and the cursor takes index 2 — the test-tone row.
    When the sinks land, keeping the *index* put the cursor on whichever
    output happened to be third, and OK there switches the television's
    audio. Nobody had moved the cursor, so nobody had chosen that row.

    Once the user has moved it (`pinned`), the row they are on is followed
    by name instead, because a rebuild also happens on every edit and the
    cursor must not jump back to the top of the panel each time. The index
    is the last resort: renaming a tile from the row above it changes that
    row's key, and staying put is better than starting over.
    """
    if not pinned:
        return None
    if previous_key:
        match = next((index for index, key in enumerate(keys) if key == previous_key), None)
        if match is not None and selectable[match]:
            return match
    if 0 <= previous_index < len(keys) and selectable[previous_index]:
        return previous_index
    return None


def _selection_offset(
    row_heights: list[int],
    selected: int,
    viewport_height: int,
    spacing: int,
    gutter: int = 0,
) -> float:
    """Return the y offset that keeps ``selected`` inside the viewport.

    `gutter` is the band each "▲ More" / "▼ More" pill occupies. They are
    opaque and were drawn over the content ("Salon an▼More" across the
    background image's value); the list carries a matching margin, so a row
    sits at `gutter + top + offset` and must stay inside the viewport less
    both pills.
    """
    if not row_heights or not 0 <= selected < len(row_heights) or viewport_height <= 0:
        return 0.0

    band = viewport_height - 2 * gutter
    content_height = sum(row_heights) + spacing * (len(row_heights) - 1)
    top = sum(row_heights[:selected]) + spacing * selected
    bottom = top + row_heights[selected]
    return max(min(0.0, float(band - content_height)), min(0.0, float(band - bottom)))
