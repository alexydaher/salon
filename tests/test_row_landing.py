# SPDX-License-Identifier: GPL-3.0-or-later
"""Which tile a vertical move lands on, given rows that keep their place."""

from salon.ui.home_row_landing import landing_column

# One row's worth of geometry at 1280x720, tile-scale 0.55: a 236px step
# over a 206px card, with the safe-area margin at 42 and 30px of bleed.
STEP = 236.0
WIDTH = 206.0
BLEED = 30.0
RESTING = 12.0  # safe_margin - bleed: the offset of a row parked at column 0


def column_at(cursor: float, *, offset: float = RESTING, count: int = 8) -> int:
    return landing_column(
        cursor, offset=offset, bleed=BLEED, step=STEP, width=WIDTH, count=count
    )


def card_center(column: int, offset: float = RESTING) -> float:
    return offset + BLEED + column * STEP + WIDTH / 2.0


def test_two_rows_at_rest_land_on_the_same_screen_position() -> None:
    """The ordinary case, and the one the change exists for: both rows are
    left-anchored on their own focused tile, so the tile under the cursor is
    the first one and the destination row does not have to move at all."""
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
