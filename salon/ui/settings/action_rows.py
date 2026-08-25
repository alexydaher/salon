# SPDX-License-Identifier: GPL-3.0-or-later
"""Action, information, and toggle settings rows."""
from __future__ import annotations

from collections.abc import Callable

from salon.ui.settings.settings_row import SettingsRow


class ActionRow(SettingsRow):
    """A row that does something. `opens` says whether RIGHT may do it.

    It defaults to the chevron this screen already draws on every row that
    leads somewhere — a section, a tile, a sub-panel — so a drill-in row
    written the same way as the existing ones is enterable without anyone
    having to remember a second flag. Rows that act rather than navigate
    ("Shut Down", "Delete row", "Add tile") are left alone: OK is a
    deliberate press, a direction key is not, and RIGHT must never be how a
    television gets turned off.
    """

    def __init__(
        self,
        label: str,
        on_activate: Callable[[], None],
        *,
        detail: str = "",
        value: str = "",
        danger: bool = False,
        icon_name: str = "",
        opens: bool | None = None,
    ) -> None:
        super().__init__(label, detail=detail, danger=danger, icon_name=icon_name)
        self._on_activate = on_activate
        self._opens = (value == "\u203a") if opens is None else opens
        self.set_value(value)

    @property
    def enterable(self) -> bool:
        return self._opens

    @property
    def hint(self) -> str:
        return "OK or RIGHT opens it" if self._opens else "OK runs it"

    def activate_row(self) -> None:
        self._on_activate()


class InfoRow(SettingsRow):
    """Read-only. Still selectable, because on a D-pad a row you cannot
    land on is a row you cannot read the end of."""

    def __init__(
        self, label: str, value: str, *, detail: str = "", icon_name: str = ""
    ) -> None:
        super().__init__(label, detail=detail, icon_name=icon_name)
        self.set_value(value)
        self.add_css_class("info")

    @property
    def hint(self) -> str:
        return "Nothing to change on this row"


class ToggleRow(SettingsRow):
    def __init__(
        self,
        label: str,
        get: Callable[[], bool],
        set_: Callable[[bool], None],
        *,
        detail: str = "",
        preview: bool = False,
    ) -> None:
        super().__init__(label, detail=detail, preview=preview)
        self._get = get
        self._set = set_
        self.refresh()

    @property
    def enterable(self) -> bool:
        """On/Off is not a list worth raising. A popup offering two items,
        one of which is what the row already says, is two presses and a
        panel to do what one press already does — and unlike a range or a
        palette there is nothing to *see* in the set of alternatives."""
        return True

    @property
    def hint(self) -> str:
        return "OK or RIGHT switches it"

    def refresh(self) -> None:
        self.set_value("On" if self._get() else "Off")

    def activate_row(self) -> None:
        self._set(not self._get())
        self.refresh()

    def can_adjust(self, delta: int) -> bool:
        return self._get() != (delta > 0)

    def adjust(self, delta: int) -> bool:
        """Still LEFT/RIGHT-able for the preview strip, which has no BACK
        of its own to protect."""
        if not self.can_adjust(delta):
            return False
        self._set(delta > 0)
        self.refresh()
        return True
