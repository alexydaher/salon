# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Focused settings-screen workflow."""

from salon.services.component import ServiceComponent
from salon.ui.settings import preview_policy
from salon.ui.settings.widgets import SettingsRow


class SettingsPreviewController(ServiceComponent):
    def _show_home_behind(self, showing: bool) -> None:
        """Collapse to a strip on the bottom edge and let the home screen
        render behind it, or put Settings back.

        Nothing is duplicated or mocked up here: the thing behind the strip
        *is* the home screen, still bound to the same GSettings keys these
        rows write, so what the user sees while adjusting is exactly what
        they get when they leave. That's the whole reason this exists —
        "Row density 85%" is not a claim anyone can evaluate.

        Two things arrive here: OPTIONS, which adjusts one row with
        LEFT/RIGHT and no list, and OK on a previewable row, which brings
        its list along and hangs it off this strip.

        `_preview_chrome` fades the home screen's own bottom row out while
        this one is up. They want the same edge of the screen and the strip
        is opaque, so what it produced was half a tile description sticking
        out from under it. Faded rather than hidden, because the band's
        bottom inset is *measured* off that row (`home_scrolling`) — hide it
        and every tile moves a few pixels the moment a preference is
        written, which is the one thing a live preview may not do.
        """
        self._owner._content.set_visible(not showing)
        self._owner._preview_bar.set_visible(showing)
        self._owner._preview_chrome(showing)
        if showing:
            self._owner.add_css_class("preview")
        else:
            self._owner.remove_css_class("preview")

    def _enter_preview(self, row: SettingsRow) -> None:
        self._owner._preview_row = row
        self._show_home_behind(True)
        self._refresh_preview()

    def _leave_preview(self) -> None:
        if self._owner._preview_row is None:
            return
        self._owner._preview_row = None
        self._show_home_behind(False)
        # The row's own value label is stale by now: the strip has been
        # writing straight through to GSettings while the list was hidden.
        self._owner._panel_list.refresh_values()

    # --- the same strip, with the row's value list open above it ---------

    def _enter_peek(self, row: SettingsRow) -> None:
        """OK on a previewable row: the list opens over the home screen.

        The value under the cursor is written as it is passed over, so the
        home screen behind answers the question the list can't — which is
        what an accent or a tile size actually looks like. What that costs
        is that leaving has to undo it, hence `_peek_restore`: BACK on this
        list promises "unchanged" everywhere else in Settings and has to
        mean it here too.
        """
        self._owner._peek_row = row
        self._owner._peek_restore = row.current_choice
        self._show_home_behind(True)
        self._owner._preview_label.set_label(row.label_text)
        self._owner._preview_hint.set_label(preview_policy.PEEK_HINT)
        self._refresh_peek()

    def _peek_candidate(self, key: str) -> None:
        """The popup's cursor moved. Only rows being previewed take this;
        every other list still changes nothing until OK."""
        row = self._owner._peek_row
        if row is None:
            return
        row.choose(key)
        self._refresh_peek()

    def _refresh_peek(self) -> None:
        row = self._owner._peek_row
        if row is None:
            return
        row.refresh()
        self._owner._preview_value.set_label(row.value_text)

    def _leave_peek(self, *, commit: bool) -> None:
        row = self._owner._peek_row
        if row is None:
            return
        self._owner._peek_row = None
        restore = self._owner._peek_restore
        self._owner._peek_restore = ""
        if not commit and restore:
            row.choose(restore)
        self._show_home_behind(False)
        self._owner._panel_list.refresh_values()

    def _refresh_preview(self) -> None:
        row = self._owner._preview_row
        if row is None:
            return
        row.refresh()
        self._owner._preview_label.set_label(row.label_text)
        self._owner._preview_value.set_label(f"‹  {row.value_text}  ›")
        self._owner._preview_hint.set_label(
            "LEFT/RIGHT adjusts · UP/DOWN changes setting · OK/BACK returns · MENU home"
        )

    def _previewable_indices(self) -> list[int]:
        return [i for i, row in enumerate(self._owner._panel_list.rows) if row.previewable]

    def _step_preview(self, delta: int) -> None:
        """UP/DOWN inside the strip walks the *previewable* rows only.

        Stepping through every row would put "Browser command" in a bar that
        has no keyboard and nothing to show behind it; these four are the
        ones the home screen answers for.
        """
        indices = self._previewable_indices()
        if not indices or self._owner._preview_row is None:
            return
        current = self._owner._panel_list.rows.index(self._owner._preview_row)
        position = indices.index(current)
        target = position + delta
        if not (0 <= target < len(indices)):
            return
        self._owner._panel_list.select(indices[target])
        self._owner._preview_row = self._owner._panel_list.rows[indices[target]]
        self._refresh_preview()
