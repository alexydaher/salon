# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure spatial focus state machine. No gi — see the AST test.

Tracks (row, col) over a grid of rows with independent lengths. The UI owns
pixels and animation; this module only ever answers "what is focused now",
synchronously, for a single Action at a time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from salon.input.actions import Action


class Bump(StrEnum):
    """Which edge a move failed to cross. The UI renders this as a short
    overshoot-and-settle; silence at a boundary reads as a broken remote."""

    NONE = "none"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class FocusChange:
    row: int
    col: int
    moved: bool
    bump: Bump = Bump.NONE


def _clamp_col(col: int, row_length: int) -> int:
    if row_length <= 0:
        return 0
    return max(0, min(col, row_length - 1))


class FocusModel:
    """Focus is never lost: every method leaves (row, col) valid for the
    current row_lengths, or (0, 0) if there are no rows at all."""

    def __init__(self, row_lengths: Sequence[int], start: tuple[int, int] = (0, 0)) -> None:
        self._row_lengths: list[int] = list(row_lengths)
        self._row = 0
        self._col = 0
        if self._row_lengths:
            self.jump_to(*start)

    @property
    def row(self) -> int:
        return self._row

    @property
    def col(self) -> int:
        return self._col

    @property
    def position(self) -> tuple[int, int]:
        return (self._row, self._col)

    def column_for(self, row: int) -> int:
        """The column this row is currently resting at.

        Every row rests at the *same* column as the focused one, clamped
        into its own length. The UI needs this for every row, not just the
        focused one, because each row scrolls independently — and if a row
        below were parked somewhere else, moving down onto it would land on
        a tile that wasn't under the cursor a moment earlier.
        """
        if row == self._row:
            return self._col
        if not (0 <= row < len(self._row_lengths)):
            return 0
        return _clamp_col(self._col, self._row_lengths[row])

    def handle(self, action: Action) -> FocusChange:
        """Only the four directions move focus; anything else is a no-op
        here (OK/BACK/etc. are handled above this layer).

        An *empty* row is passable, not a trap. Refusing every direction
        while resting on one — which is what this did before — meant a row
        whose provider returned nothing, or one the user had just added in
        the editor, permanently swallowed the focus: nothing moved again
        until Salon was restarted. Vertical movement still works out of an
        empty row; only LEFT/RIGHT have nowhere to go, and they rubber-band.
        """
        if not self._row_lengths:
            return FocusChange(self._row, self._col, moved=False)
        if action is Action.UP:
            return self._move_vertical(-1)
        if action is Action.DOWN:
            return self._move_vertical(1)
        if action is Action.LEFT:
            return self._move_horizontal(-1)
        if action is Action.RIGHT:
            return self._move_horizontal(1)
        return FocusChange(self._row, self._col, moved=False)

    def set_row_lengths(self, row_lengths: Sequence[int]) -> FocusChange:
        """The catalog changed shape (provider refresh, tile add/remove).

        Recovers to the nearest surviving row at or before the current row
        index, then clamps the column into that row's new bounds. Precise
        "same tile" recovery (by id) is the caller's job — resolve the
        focused tile id to a target (row, col) in the new catalog first and
        call jump_to() instead when that's possible.
        """
        self._row_lengths = list(row_lengths)
        if not self._row_lengths:
            self._row = 0
            self._col = 0
            return FocusChange(0, 0, moved=False)
        self._row = min(self._row, len(self._row_lengths) - 1)
        self._col = _clamp_col(self._col, self._row_lengths[self._row])
        return FocusChange(self._row, self._col, moved=False)

    def jump_to(self, row: int, col: int) -> FocusChange:
        """Used for startup restoration (from a persisted tile id resolved
        to indices by the caller) and for entry points like search."""
        if not self._row_lengths:
            self._row = 0
            self._col = 0
            return FocusChange(0, 0, moved=False)
        self._row = max(0, min(row, len(self._row_lengths) - 1))
        self._col = _clamp_col(col, self._row_lengths[self._row])
        return FocusChange(self._row, self._col, moved=True)

    def _move_vertical(self, delta: int) -> FocusChange:
        new_row = self._row + delta
        if not (0 <= new_row < len(self._row_lengths)):
            return FocusChange(
                self._row, self._col, moved=False, bump=Bump.UP if delta < 0 else Bump.DOWN
            )
        self._row = new_row
        # The column carries across rows rather than being remembered per
        # row: moving down should land on the tile directly below the one
        # that was focused, not wherever this row happened to be left. A
        # shorter row clamps, and moving back up returns to the clamped
        # column, not the original — the alternative is a cursor that
        # travels sideways on its own, which reads as drift.
        self._col = _clamp_col(self._col, self._row_lengths[new_row])
        return FocusChange(self._row, self._col, moved=True)

    def _move_horizontal(self, delta: int) -> FocusChange:
        new_col = self._col + delta
        row_length = self._row_lengths[self._row]
        if not (0 <= new_col < row_length):
            return FocusChange(
                self._row, self._col, moved=False, bump=Bump.LEFT if delta < 0 else Bump.RIGHT
            )
        self._col = new_col
        return FocusChange(self._row, self._col, moved=True)
