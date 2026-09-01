# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Raising a row's values control, and what comes back from it.

One press — OK, or a click — reaches three different places from here: the
popup, the live-preview strip that a previewable row collapses the screen
to, and the rebuild that follows a choice. Split out of `screen_actions`,
which is the map from a button to a meaning; this is what one of those
meanings then does.
"""

from salon.services.component import ServiceComponent
from salon.ui.settings import preview_policy
from salon.ui.settings.screen_shared import Gtk, SettingsRow


class SettingsValuesController(ServiceComponent):
    def _activate_panel_row(self, index: int) -> None:
        """A click, taking the same path OK does — including the collapse
        to the home screen on a previewable row, because one row has to
        mean one thing whichever device pressed it. What made that too
        startling for a click before was the *bare* strip, with nothing
        left to click; the list comes with it now."""
        row = self._owner._panel_list.rows[index]
        if row.choices:
            self._open_values(row)
        else:
            row.activate_row()

    def _open_values(self, row: SettingsRow) -> None:
        """Raise the row's values.

        On a previewable row Settings gets out of the way first and the
        control opens over the live home screen, embedded in the strip along
        the bottom because the row it belongs to is no longer drawn. That
        is the whole of the feature: an accent, a tile size or a row
        density is a claim about the home screen, and this is the press
        where the user is deciding it.
        """
        peek = preview_policy.previews_home(row.previewable, bool(row.choices))
        if peek:
            self._owner._enter_peek(row)
        opened = self._owner._popup.open_for(
            row,
            inline=self._owner._preview_bar.choices if peek else None,
            position=Gtk.PositionType.BOTTOM,
        )
        if not opened:
            # Nothing to steer the collapsed screen with. Put it back.
            self._owner._leave_peek(commit=False)
            return
        self._owner._update_legend()

    def _on_value_chosen(self) -> None:
        """A value was picked. The row has already written it; everything
        else on the panel may now be describing the old one — a tile's kind
        decides which rows exist below it — so rebuild rather than guess."""
        self._owner._leave_peek(commit=True)
        self._owner._rebuild_panel()

    def _on_value_dismissed(self) -> None:
        """The list went away without a choice: BACK, MENU, or the screen
        navigating out from under it. Anything live preview wrote while the
        cursor walked the list is undone here — otherwise BACK would leave
        whichever value happened to be passed over last, which is the one
        thing every other list in Settings promises it will not do."""
        self._owner._leave_peek(commit=False)
