# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Where a direction press puts the cursor, and what it moves to get there.

The rule this exists to serve is in `home_row_landing`: a row is scrolled
only while the cursor is inside it, so a vertical press has to work out
which tile of the destination is already under the ring rather than
assuming every row is parked at the same column.
"""

from salon.services.component import ServiceComponent
from salon.ui.home_row_landing import landing_column
from salon.ui.home_shared import Action, Bump


class HomeLandingController(ServiceComponent):
    def _move_focus(self, action: Action) -> None:
        """One of the four directions, on the home screen's own tiles."""
        # Read before the model moves: it is the position the ring is
        # leaving, and the destination row lands whichever of its own tiles
        # is already under it. Only the vertical presses need it — LEFT and
        # RIGHT stay inside one row, which owns its own column.
        vertical = action is Action.UP or action is Action.DOWN
        cursor_center = self._cursor_center_x() if vertical else None
        change = self._owner._focus.handle(action)
        if change.moved:
            if vertical:
                self._land_in_row(change.row, cursor_center)
            self._owner._update_focus()
        elif change.bump is Bump.UP:
            # The top of the tiles is not a wall: it's the top bar. This is
            # the whole reason Search/Settings/Power are reachable at all
            # without knowing that MENU exists.
            self._owner._set_nav_focused(True)
        elif change.bump is not Bump.NONE:
            self._owner._rubber_band(change.bump)

    def _cursor_center_x(self) -> float | None:
        """Where the focus ring sits across the screen, in row coordinates.

        The row's *resting* offset rather than the spring's current value: a
        held direction key starts the next move while the last one is still
        travelling, and landing on whichever tile a half-finished animation
        happened to have under the cursor would make the same press mean
        different things at different speeds.
        """
        index = self._owner._focus.row
        if not (0 <= index < len(self._owner._rows)):
            return None
        row = self._owner._rows[index]
        if not row.tiles:
            return None
        offset = self._owner._row_scroll_x(row, self._owner._focus.col)
        return (
            offset
            + row.metrics.bleed
            + self._owner._focus.col * row.metrics.step
            + row.metrics.width / 2.0
        )

    def _land_in_row(self, row_index: int, cursor_center: float | None) -> None:
        """Put the cursor on the tile already under it, without moving the row.

        Called after the focus model has agreed the vertical move is legal,
        because the model owns the row bounds and the rubber-band, and this
        owns only which column of the destination the ring appears on.
        """
        if not (0 <= row_index < len(self._owner._rows)):
            return
        row = self._owner._rows[row_index]
        if cursor_center is None or not row.tiles:
            return
        column = landing_column(
            cursor_center,
            offset=self._owner._row_scroll_x(row, row.column),
            bleed=row.metrics.bleed,
            step=row.metrics.step,
            width=row.metrics.width,
            count=len(row.tiles),
        )
        self._owner._focus.jump_to(row_index, column)
