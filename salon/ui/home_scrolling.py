# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused home-view workflow."""

from salon.services.component import ServiceComponent
from salon.ui.home_shared import _FALLBACK_VIEWPORT_HEIGHT_PX, Bump, tokens


class HomeScrollController(ServiceComponent):
    def _top_inset(self) -> float:
        """How much of the top of the screen the rows may not use.

        Measured off the two status widgets rather than taken from
        STATUS_BAR_HEIGHT_DU, for the same reason `_bottom_inset` is
        measured: both carry their own safe-area top margin and both scale
        with the du pipeline, and the token is a design figure rather than
        what the widgets actually ask for. The larger of the two, because
        they are side by side — the buttons are taller than the clock.
        """
        natural = max(
            self._owner._status_info.get_preferred_size()[1].height,
            self._owner._status_bar.get_preferred_size()[1].height,
        )
        if natural > 0:
            return float(natural)
        return self._owner._safe_margin + self._owner._status_height

    def _bottom_inset(self) -> float:
        """How much of the bottom of the screen the rows may not use.

        Measured off the detail strip rather than taken from a constant:
        the strip is two lines of type plus its own bottom margin, all of
        which move with the du scale and with the safe-area preference, and
        a guessed constant was 104px against a real 165 — sixty pixels of
        rows scrolling underneath text.
        """
        natural = self._owner._detail_bar.get_preferred_size()[1].height
        if natural > 0:
            return float(natural)
        return self._owner._safe_margin + self._owner._detail_height

    def _row_anchor_y(self) -> float:
        """The focused row holds a fixed vertical anchor (§6.1), clamped at
        both ends of the content.

        In **band** coordinates: the scrolling viewport no longer spans the
        window, it spans the gap between the top bar and the detail strip
        (`_apply_viewport_insets`), so 0 here is the top of that gap and not
        the top of the screen. The anchor line itself is still measured on
        the *window*, because 38% of a television is a design figure about
        where a human looks and not about where this widget happens to
        start — hence the `- top_inset` converting it back.

        The top clamp keeps a catalogue shorter than the band sitting at the
        top of it rather than floating in the middle of dead space. The
        bottom clamp stops the stack scrolling past its own end.

        That bottom clamp was removed once, because it left barely 90px of
        travel on a four-row 1080p screen and parked the last row under the
        fold with its tiles half off. The diagnosis was right and the cure
        was wrong: the fault was a limit that ignored the insets, not the
        existence of a limit. Computed properly the last row lands fully
        visible with the detail strip beneath it, and the case the removal
        caused goes away too: with three rows and the cursor on the last of
        them, an unclamped anchor scrolled 409px into empty space and left
        sixty per cent of a television blank.
        """
        band_height = self._owner._viewport_height or _FALLBACK_VIEWPORT_HEIGHT_PX
        top_inset = self._top_inset()
        window_height = band_height + top_inset + self._bottom_inset()
        content_height = self._owner._content_height()

        if content_height <= band_height:
            return 0.0

        focused_center = (
            self._owner._row_tile_top(self._owner._focus.row)
            + self._owner._focused_tile_height() / 2.0
        )
        anchor_line = window_height * tokens.ROW_ANCHOR_FRACTION - top_inset
        desired = anchor_line - focused_center
        lowest = band_height - content_height
        return min(0.0, max(lowest, desired))

    def _update_row_anchor(self, *, animate: bool) -> None:
        target = self._row_anchor_y()
        self._owner._row_anchor.animate_to(target) if animate else self._owner._row_anchor.jump_to(
            target
        )

    def _rubber_band(self, bump: Bump) -> None:
        distance = self._owner._bump_distance
        if bump is Bump.LEFT or bump is Bump.RIGHT:
            if not (0 <= self._owner._focus.row < len(self._owner._rows)):
                return
            scroller = self._owner._rows[self._owner._focus.row].scroller
            scroller.bump(distance if bump is Bump.LEFT else -distance)
        elif bump is Bump.UP:
            self._owner._row_anchor.bump(distance)
        elif bump is Bump.DOWN:
            self._owner._row_anchor.bump(-distance)
