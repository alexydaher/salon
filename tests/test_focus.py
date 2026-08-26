# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from salon.core.focus import Bump, FocusModel
from salon.input.actions import Action


def test_starts_at_origin_by_default() -> None:
    model = FocusModel([3, 4, 2])
    assert model.position == (0, 0)


def test_horizontal_movement() -> None:
    model = FocusModel([3, 4, 2])
    change = model.handle(Action.RIGHT)
    assert change.row == 0
    assert change.col == 1
    assert change.moved is True


def test_no_wraparound_left_bumps() -> None:
    model = FocusModel([3])
    change = model.handle(Action.LEFT)
    assert change.moved is False
    assert change.bump is Bump.LEFT
    assert model.position == (0, 0)


def test_no_wraparound_right_bumps_at_row_end() -> None:
    model = FocusModel([3])
    model.handle(Action.RIGHT)
    model.handle(Action.RIGHT)
    change = model.handle(Action.RIGHT)
    assert change.moved is False
    assert change.bump is Bump.RIGHT
    assert model.position == (0, 2)


def test_no_wraparound_up_bumps_at_first_row() -> None:
    model = FocusModel([3, 3])
    change = model.handle(Action.UP)
    assert change.moved is False
    assert change.bump is Bump.UP


def test_no_wraparound_down_bumps_at_last_row() -> None:
    model = FocusModel([3, 3])
    model.handle(Action.DOWN)
    change = model.handle(Action.DOWN)
    assert change.moved is False
    assert change.bump is Bump.DOWN


def test_vertical_movement_restores_each_rows_column() -> None:
    model = FocusModel([5, 5])
    for _ in range(4):
        model.handle(Action.RIGHT)
    assert model.position == (0, 4)
    model.handle(Action.DOWN)
    assert model.position == (1, 0)
    model.handle(Action.RIGHT)
    assert model.position == (1, 1)
    model.handle(Action.UP)
    assert model.position == (0, 4)
    model.handle(Action.DOWN)
    assert model.position == (1, 1)


def test_vertical_movement_does_not_clamp_another_rows_memory() -> None:
    model = FocusModel([5, 2])
    for _ in range(4):
        model.handle(Action.RIGHT)
    model.handle(Action.DOWN)
    assert model.position == (1, 0)
    model.handle(Action.UP)
    assert model.position == (0, 4)


def test_column_clamped_if_row_shrank() -> None:
    model = FocusModel([5, 5])
    for _ in range(4):
        model.handle(Action.RIGHT)
    change = model.set_row_lengths([2, 5])
    assert change.row == 0
    assert change.col == 1


def test_set_row_lengths_recovers_to_nearest_row_when_current_row_removed() -> None:
    model = FocusModel([3, 3, 3], start=(2, 1))
    change = model.set_row_lengths([3, 3])
    assert change.row == 1
    assert change.col == 0


def test_set_row_lengths_with_no_rows_resets_to_origin() -> None:
    model = FocusModel([3, 3])
    change = model.set_row_lengths([])
    assert change.row == 0
    assert change.col == 0
    assert model.position == (0, 0)


def test_handle_is_noop_after_catalog_becomes_empty() -> None:
    model = FocusModel([3])
    model.set_row_lengths([])
    change = model.handle(Action.RIGHT)
    assert change.moved is False
    assert model.position == (0, 0)


def test_jump_to_clamps_out_of_range_position() -> None:
    model = FocusModel([3, 2])
    change = model.jump_to(1, 10)
    assert change.row == 1
    assert change.col == 1


def test_jump_to_column_carries_through_a_vertical_round_trip() -> None:
    model = FocusModel([5, 5])
    model.jump_to(0, 3)
    model.handle(Action.DOWN)
    model.handle(Action.UP)
    assert model.position == (0, 3)


def test_ok_and_back_are_noops_for_focus_position() -> None:
    model = FocusModel([3, 3])
    before = model.position
    change = model.handle(Action.OK)
    assert change.moved is False
    assert model.position == before


def test_column_for_reports_independent_row_memory() -> None:
    model = FocusModel([4, 4, 4])
    for _ in range(3):
        model.handle(Action.RIGHT)
    assert model.column_for(0) == 3

    model.handle(Action.DOWN)
    assert model.column_for(0) == 3
    assert model.column_for(1) == 0
    assert model.column_for(2) == 0


def test_column_for_clamps_to_a_shorter_row() -> None:
    model = FocusModel([5, 2])
    for _ in range(4):
        model.handle(Action.RIGHT)
    assert model.column_for(0) == 4
    assert model.column_for(1) == 0


def test_column_for_out_of_range_row_is_zero() -> None:
    model = FocusModel([3])
    assert model.column_for(7) == 0


def test_empty_row_does_not_trap_focus() -> None:
    """A row with no tiles must stay passable in both vertical directions.

    Regression: `handle()` used to refuse every action while resting on an
    empty row, so a provider that returned nothing (or a row just added in
    the editor) swallowed the focus for the rest of the session.
    """
    model = FocusModel([3, 0, 2])

    assert model.handle(Action.DOWN).moved is True
    assert model.position == (1, 0)

    # Nowhere to go sideways, but it bumps rather than sitting silent.
    sideways = model.handle(Action.RIGHT)
    assert sideways.moved is False
    assert sideways.bump is Bump.RIGHT

    model.handle(Action.DOWN)
    assert model.position == (2, 0)
    model.handle(Action.UP)
    assert model.position == (1, 0)
    model.handle(Action.UP)
    assert model.position == (0, 0)
