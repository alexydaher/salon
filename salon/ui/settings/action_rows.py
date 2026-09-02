# SPDX-License-Identifier: GPL-3.0-or-later
"""The rows that do something: an action, and a switch."""

from __future__ import annotations

from collections.abc import Callable

from salon.ui.settings.settings_row import SettingsRow

_CHEVRON = "›"


class ActionRow(SettingsRow):
    """A row that does something. `opens` says whether RIGHT may do it.

    It defaults to the chevron this screen already draws on every row that
    leads somewhere — a section, a tile, a sub-panel — so a drill-in row
    written the same way as the existing ones is enterable without anyone
    having to remember a second flag. Rows that act rather than navigate
    ("Shut Down", "Delete row", "Add tile") are left alone: OK is a
    deliberate press, a direction key is not, and RIGHT must never be how a
    television gets turned off.

    `external=True` marks the ones that leave Salon for GNOME's own
    settings. Those used to be the same shape of row as "Suspend", so
    "Display and resolution" and "power the machine off" were typographically
    identical from three metres.
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
        external: bool = False,
    ) -> None:
        super().__init__(
            label, detail=detail, danger=danger, icon_name=icon_name, external=external
        )
        self._on_activate = on_activate
        self._opens = (value == _CHEVRON) if opens is None else opens
        self.set_value(value, muted=value == _CHEVRON)

    @property
    def enterable(self) -> bool:
        return self._opens

    @property
    def hint(self) -> str:
        if self.external:
            return "OK opens GNOME Settings"
        return "OK or RIGHT opens it" if self._opens else "OK runs it"

    def activate_row(self) -> None:
        self._on_activate()


def opens_panel(
    label: str, on_activate: Callable[[], None], *, detail: str = "", icon_name: str = ""
) -> ActionRow:
    """A row that drills into another panel. Named rather than repeated:
    `value="›"` appeared at two dozen call sites as the way to say this,
    which made the chevron look like decoration rather than a contract."""
    return ActionRow(
        label, on_activate, detail=detail, value=_CHEVRON, icon_name=icon_name, opens=True
    )


def opens_gnome(label: str, on_activate: Callable[[], None], *, detail: str = "") -> ActionRow:
    """A row that hands over to gnome-control-center (§1)."""
    return ActionRow(label, on_activate, detail=detail, value="↗", external=True)


def opens_picker(label: str, on_activate: Callable[[], None], *, detail: str = "") -> ActionRow:
    """A row that raises a file chooser.

    The same contract as `opens_panel` — something opens, RIGHT may open it,
    BACK comes back with nothing changed — and drawn the same way, because
    "Choose a picture…" carrying no affordance at all beside "Type a path…"
    carrying a chevron said the two were different kinds of row.
    """
    return ActionRow(label, on_activate, detail=detail, value=_CHEVRON, opens=True)


class ToggleRow(SettingsRow):
    """On or off, drawn as a switch rather than spelled as a word.

    The value column is `@accent`, so a row reading "Off" used to render
    that word in the brightest colour on the screen — the disabled state
    announcing itself as the enabled one. A pill has a position as well as
    a colour and cannot be misread at three metres.
    """

    def __init__(
        self,
        label: str,
        get: Callable[[], bool],
        set_: Callable[[bool], None],
        *,
        detail: str = "",
        preview: bool = False,
        default: bool | None = None,
    ) -> None:
        super().__init__(label, detail=detail, preview=preview)
        self._get = get
        self._set = set_
        self._default = default
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

    @property
    def modified(self) -> bool:
        return self._default is not None and self._get() != self._default

    def reset_to_default(self) -> bool:
        if self._default is None or self._get() == self._default:
            return False
        self._set(self._default)
        self.refresh()
        return True

    def refresh(self) -> None:
        on = self._get()
        # The word goes with the pill for a screen reader and for anyone
        # who wants it spelled out; it is muted when off so the accent
        # never means "not doing anything".
        self.set_value("On" if on else "Off", muted=not on)
        self._content.set_switch(on)

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
