# SPDX-License-Identifier: GPL-3.0-or-later
"""Horizontal home-row navigation keeps still until a visible edge."""

import pytest

from salon.ui.home_row_landing import (
    landing_column,
    revealed_scroll_position,
    row_scroll_offset,
)

# One row's worth of geometry at 1280x720, tile-scale 0.55: a 236px step
# over a 206px card, with the safe-area margin at 42 and 30px of bleed.
STEP = 236.0
WIDTH = 206.0
BLEED = 30.0
RESTING = 12.0  # safe_margin - bleed: the offset of a row parked at column 0
VIEWPORT = 1280.0
SAFE = 42.0
CONTENT = 8 * STEP - (STEP - WIDTH)


def column_at(cursor: float, *, offset: float = RESTING, count: int = 8) -> int:
    return landing_column(
        cursor, offset=offset, bleed=BLEED, step=STEP, width=WIDTH, count=count
    )


def visible_column_at(cursor: float, *, offset: float = RESTING, count: int = 8) -> int:
    return landing_column(
        cursor,
        offset=offset,
        bleed=BLEED,
        step=STEP,
        width=WIDTH,
        count=count,
        viewport_width=VIEWPORT,
        safe_margin=SAFE,
    )


def reveal(column: int, position: float = 0.0, *, content: float = CONTENT) -> float:
    return revealed_scroll_position(
        column,
        position,
        viewport_width=VIEWPORT,
        safe_margin=SAFE,
        bleed=BLEED,
        step=STEP,
        width=WIDTH,
        content_width=content,
    )


def card_center(column: int, offset: float = RESTING) -> float:
    return offset + BLEED + column * STEP + WIDTH / 2.0


def test_two_rows_at_rest_land_on_the_same_screen_position() -> None:
    """Equal row geometry aligns cards without moving either row."""
    assert column_at(card_center(0)) == 0


def test_a_row_scrolled_elsewhere_lands_under_the_cursor() -> None:
    """A row parked five tiles along still lands the ring where the eye is:
    the tile at the cursor's x, not the fifth tile of that row."""
    offset = RESTING - 5 * STEP
    assert column_at(card_center(0), offset=offset) == 5


def test_the_nearest_card_wins_when_the_rows_are_misaligned() -> None:
    """A row clamped against its own end sits at a fraction of a step, so no
    card lines up exactly. The ring goes to the nearer of the two."""
    assert column_at(card_center(3) + STEP * 0.4) == 3
    assert column_at(card_center(3) + STEP * 0.6) == 4


def test_a_cursor_exactly_between_two_cards_rounds_the_same_way_everywhere() -> None:
    """Half away from zero, not to even: `round()` would send an
    exactly-between cursor left from column 2 and right from column 3."""
    assert column_at(card_center(2) + STEP / 2.0) == 3
    assert column_at(card_center(3) + STEP / 2.0) == 4


def test_a_short_row_clamps_to_its_last_tile() -> None:
    assert column_at(card_center(9), count=3) == 2


def test_a_cursor_left_of_the_row_clamps_to_the_first_tile() -> None:
    assert column_at(card_center(0) - 4 * STEP) == 0


def test_an_empty_row_lands_at_zero() -> None:
    assert column_at(card_center(4), count=0) == 0


def test_a_degenerate_step_lands_at_zero_rather_than_dividing_by_it() -> None:
    assert landing_column(500.0, offset=0.0, bleed=0.0, step=0.0, width=0.0, count=4) == 0


def test_down_from_the_end_of_a_short_row_does_not_move_the_long_row() -> None:
    """The reported edge case: column two of a fitting source row is far
    from the left anchor. The destination selects column two beneath it and
    keeps its existing position instead of pulling that card to the left."""
    cursor = card_center(2)
    landed = visible_column_at(cursor)

    assert landed == 2
    assert reveal(landed) == 0.0


def test_vertical_landing_ignores_a_card_only_peeking_past_the_safe_edge() -> None:
    """A clipped card would require a second, horizontal movement after
    the ring arrived. Land on the nearest complete card instead."""
    assert column_at(1260.0) == 5
    assert visible_column_at(1260.0) == 4
    assert reveal(4) == 0.0


def test_entering_a_previously_scrolled_row_keeps_its_position() -> None:
    position = 2.0
    offset = row_scroll_offset(
        position,
        viewport_width=VIEWPORT,
        safe_margin=SAFE,
        bleed=BLEED,
        step=STEP,
        content_width=CONTENT,
    )
    landed = visible_column_at(card_center(4), offset=offset)

    assert landed == 6
    assert reveal(landed, position) == position


def test_horizontal_focus_crosses_visible_cards_without_dragging_the_row() -> None:
    assert [reveal(column) for column in range(5)] == [0.0] * 5


def test_crossing_the_right_safe_edge_reveals_only_the_overflow() -> None:
    position = reveal(5)
    expected_overflow = card_center(5) + WIDTH / 2.0 - (VIEWPORT - SAFE)

    assert position == pytest.approx(expected_overflow / STEP)
    assert 0.0 < position < 1.0


def test_reversing_direction_does_not_snap_back_to_a_column_anchor() -> None:
    position = reveal(5)

    assert reveal(4, position) == pytest.approx(position)
    assert reveal(3, position) == pytest.approx(position)


def test_a_row_that_fits_never_scrolls_even_when_asked_for_its_last_card() -> None:
    three_cards = 3 * STEP - (STEP - WIDTH)

    assert reveal(2, content=three_cards) == 0.0


def test_pixel_offset_is_reclamped_when_the_viewport_grows() -> None:
    narrow = row_scroll_offset(
        99.0,
        viewport_width=VIEWPORT,
        safe_margin=SAFE,
        bleed=BLEED,
        step=STEP,
        content_width=CONTENT,
    )
    wide = row_scroll_offset(
        99.0,
        viewport_width=2000.0,
        safe_margin=SAFE,
        bleed=BLEED,
        step=STEP,
        content_width=CONTENT,
    )

    assert narrow == pytest.approx(VIEWPORT - SAFE - BLEED - CONTENT)
    assert wide == RESTING
