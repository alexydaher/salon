# SPDX-License-Identifier: GPL-3.0-or-later
"""What every settings row promises, and the harmless answer to each.

A plain mixin under `SettingsRow`, not a second widget: these are the
questions the screen asks a row it knows nothing else about — has it a list
of values, may RIGHT act on it, has it been changed, what does the legend
say — and every one of them has an answer that is safe for a row that does
none of those things. Keeping the defaults here leaves `settings_row.py`
holding the state machine alone, which is the job its docstring claims.

Subtypes override what they mean. Nothing in here touches a widget, so a
row subtype can be read against this file without reading GTK.
"""

from __future__ import annotations


class RowContract:
    @property
    def choices(self) -> list[tuple[str, str]]:
        """The values this row can take, as (key, label). Non-empty means OK
        raises the list rather than changing anything itself. The key is
        opaque outside the row; only `current_choice` and `choose` read it."""
        return []

    @property
    def current_choice(self) -> str:
        """Which of `choices` is set, by key. Empty selects nothing."""
        return ""

    def choose(self, key: str) -> None:
        """Apply one of `choices`. Called from the popup, never directly."""

    @property
    def swatches(self) -> dict[str, str]:
        """Colour for any of `choices` that names one, keyed the same way.
        The popup draws these beside the labels: a list reading "Ember",
        "Cold blue", "Violet" is a list of words about colours."""
        return {}

    @property
    def enterable(self) -> bool:
        """True for rows where RIGHT may safely do the thing directly: no
        list to raise, and nothing lost by a stray press."""
        return False

    @property
    def modified(self) -> bool:
        """Whether this row holds something other than what Salon shipped."""
        return False

    def reset_to_default(self) -> bool:
        """Put the shipped value back. False when there is nothing to undo."""
        return False

    @property
    def hint(self) -> str:
        """What the legend at the bottom of the screen says about this row."""
        return "OK selects"

    def activate_row(self) -> None:
        """OK, or a click."""

    def can_adjust(self, delta: int) -> bool:
        """Whether a step in this direction would change anything. With
        `choices` this only serves the preview strip, which is the one place
        LEFT/RIGHT still moves a value."""
        return False

    def adjust(self, delta: int) -> bool:
        """One step, for the preview strip. False if it ran off the end, so
        the caller can say so rather than doing nothing silently."""
        return False

    def refresh(self) -> None:
        """Re-read the underlying value. Called when the list is shown, so
        a row never displays state that changed elsewhere."""
