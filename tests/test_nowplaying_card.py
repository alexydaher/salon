# SPDX-License-Identifier: GPL-3.0-or-later
"""What the console rail's now-playing card shows, and where its cursor is."""

from salon.core.actions import Action
from salon.core.nowplaying_card import (
    HEADING,
    CardCursor,
    CardKey,
    card_rows,
    clamp_cursor,
    entry_cursor,
    key_at,
    move_cursor,
    select_source,
    source_position,
    step_source,
)


def test_the_position_is_only_printed_when_there_is_something_to_pick() -> None:
    assert HEADING == "NOW PLAYING"
    assert source_position(0, 0) == ""
    assert source_position(0, 1) == ""
    assert source_position(1, 3) == "2/3"


def test_the_position_survives_an_index_the_snapshot_has_outgrown() -> None:
    # A player quitting shortens the list before the card has redrawn.
    assert source_position(7, 3) == "3/3"
    assert source_position(-2, 3) == "1/3"


def test_the_picker_wraps_rather_than_stopping_at_an_end() -> None:
    """A key that stops working at an end of a list nobody can see the
    extent of reads as broken from the sofa."""
    assert step_source(2, 3, forward=True) == 0
    assert step_source(0, 3, forward=False) == 2
    assert step_source(0, 3, forward=True) == 1
    assert step_source(0, 0, forward=True) == 0


def test_the_card_follows_the_source_it_was_showing_not_its_slot() -> None:
    sources = ["a", "b", "c"]
    assert select_source(sources, "c", "a") == 2
    # The chosen one has moved down the list; the card moves with it.
    assert select_source(["z", "a", "c"], "c", "a") == 2


def test_a_source_that_has_gone_falls_back_to_the_watcher_then_the_first() -> None:
    assert select_source(["a", "b"], "gone", "b") == 1
    assert select_source(["a", "b"], "gone", "also-gone") == 0
    assert select_source(["a", "b"], "", "") == 0


def test_the_picker_row_exists_only_while_there_is_a_second_source() -> None:
    assert card_rows(1) == (
        (CardKey.PREVIOUS_TRACK, CardKey.PLAY_PAUSE, CardKey.NEXT_TRACK),
    )
    assert card_rows(3)[0] == (CardKey.PREVIOUS_SOURCE, CardKey.NEXT_SOURCE)
    assert len(card_rows(3)) == 2


def test_a_press_in_from_the_tiles_lands_on_the_play_key() -> None:
    for count in (1, 2, 5):
        rows = card_rows(count)
        assert key_at(rows, entry_cursor(rows)) is CardKey.PLAY_PAUSE


def test_right_off_the_end_of_a_row_is_the_way_back_to_the_tiles() -> None:
    """The rail is the screen's left edge, so out is rightwards."""
    rows = card_rows(2)
    assert move_cursor(rows, CardCursor(1, 2), Action.RIGHT) is None
    assert move_cursor(rows, CardCursor(0, 1), Action.RIGHT) is None
    assert move_cursor(rows, CardCursor(1, 0), Action.RIGHT) == CardCursor(1, 1)


def test_every_other_edge_holds_so_the_arrows_cannot_be_stranded() -> None:
    rows = card_rows(2)
    assert move_cursor(rows, CardCursor(0, 0), Action.LEFT) == CardCursor(0, 0)
    assert move_cursor(rows, CardCursor(0, 0), Action.UP) == CardCursor(0, 0)
    assert move_cursor(rows, CardCursor(1, 2), Action.DOWN) == CardCursor(1, 2)


def test_crossing_between_the_picker_and_the_transport_clamps_the_column() -> None:
    rows = card_rows(2)
    assert move_cursor(rows, CardCursor(0, 1), Action.DOWN) == CardCursor(1, 1)
    assert move_cursor(rows, CardCursor(1, 2), Action.UP) == CardCursor(0, 1)


def test_a_cursor_held_across_a_snapshot_lands_on_a_row_that_still_exists() -> None:
    """The picker row goes when the second source does, and the ring can be
    sitting in it at the time."""
    assert clamp_cursor(card_rows(1), CardCursor(1, 1)) == CardCursor(0, 1)
    assert clamp_cursor(card_rows(2), CardCursor(0, 9)) == CardCursor(0, 1)
    assert clamp_cursor((), CardCursor(3, 3)) == CardCursor(0, 0)
    assert key_at((), CardCursor()) is None
    assert move_cursor((), CardCursor(), Action.LEFT) is None
