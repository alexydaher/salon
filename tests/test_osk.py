# SPDX-License-Identifier: GPL-3.0-or-later
"""The on-screen keyboard's layout and cursor (§6.6)."""

from __future__ import annotations

from salon.core.osk import GRID_COLUMNS, LAYOUT, KeyboardModel, KeyKind
from salon.input.actions import Action


def test_every_row_is_the_same_grid_width() -> None:
    """Ragged key *counts* are fine; ragged total widths are not, or the
    spatial vertical navigation lands on nothing at the right-hand edge."""
    for row in LAYOUT:
        assert sum(key.width for key in row) == GRID_COLUMNS


def test_the_required_action_keys_all_exist() -> None:
    kinds = {key.kind for row in LAYOUT for key in row}
    assert {KeyKind.SPACE, KeyKind.BACKSPACE, KeyKind.SHIFT, KeyKind.DONE} <= kinds


def test_typing_accumulates_text() -> None:
    model = KeyboardModel()
    for _ in range(3):  # q, w, e
        model.press()
        model.move(Action.RIGHT)
    assert model.text == "qwe"


def test_shift_is_one_shot() -> None:
    model = KeyboardModel()
    model.jump_to(4, 0)  # Shift
    model.press()
    assert model.shift is True
    model.jump_to(1, 0)  # q
    model.press()
    model.press()
    assert model.text == "Qq"
    assert model.shift is False


def test_backspace_on_empty_text_is_harmless() -> None:
    model = KeyboardModel()
    model.jump_to(4, 2)
    assert model.press().text == ""
    assert model.press().changed is False


def test_done_reports_done_without_changing_text() -> None:
    model = KeyboardModel("hi")
    model.jump_to(4, 3)
    result = model.press()
    assert result.done is True
    assert result.text == "hi"


def test_vertical_movement_is_spatial_not_by_index() -> None:
    """ "b" is the fifth key of its row but sits over grid cell 4, which is
    inside Space's 2-5 span. Moving by index instead would clamp to the last
    key of the four-key bottom row — Done — which is nowhere near it."""
    model = KeyboardModel()
    model.jump_to(3, 4)  # "b"
    assert model.key.value == "b"
    model.move(Action.DOWN)
    assert model.key.kind is KeyKind.SPACE


def test_vertical_movement_lands_under_the_cursor_not_under_the_row() -> None:
    """ "m" is index 6 and lands on Backspace, which is index 2 — the two
    numbers have nothing to do with each other, which is the point."""
    model = KeyboardModel()
    model.jump_to(3, 6)  # "m", over grid cell 6
    model.move(Action.DOWN)
    assert model.key.kind is KeyKind.BACKSPACE


def test_wide_keys_map_back_up_to_the_key_above_their_centre() -> None:
    model = KeyboardModel()
    model.jump_to(4, 0)  # Shift, spanning cells 0-1
    model.move(Action.UP)
    assert model.key.value == "z"


def test_edges_report_failure_so_the_caller_can_cross_panes() -> None:
    model = KeyboardModel()
    model.jump_to(1, 0)
    assert model.move(Action.LEFT) is False
    model.jump_to(1, len(LAYOUT[1]) - 1)
    assert model.move(Action.RIGHT) is False
    model.jump_to(0, 0)
    assert model.move(Action.UP) is False
    model.jump_to(len(LAYOUT) - 1, 0)
    assert model.move(Action.DOWN) is False


def test_jump_to_clamps_into_a_shorter_row() -> None:
    model = KeyboardModel()
    model.jump_to(4, 99)
    assert model.position == (4, len(LAYOUT[4]) - 1)


def test_set_text_replaces_without_moving_the_cursor() -> None:
    model = KeyboardModel()
    model.jump_to(2, 3)
    before = model.position
    model.set_text("from phone")
    assert model.text == "from phone"
    assert model.position == before


def test_hardware_text_can_be_inserted_and_deleted() -> None:
    model = KeyboardModel("hello")
    assert model.insert_text(" world") is True
    assert model.text == "hello world"
    assert model.backspace() is True
    assert model.text == "hello worl"


def test_hardware_text_empty_edits_are_harmless() -> None:
    model = KeyboardModel()
    assert model.insert_text("") is False
    assert model.backspace() is False
