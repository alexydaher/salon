# SPDX-License-Identifier: GPL-3.0-or-later
"""The two rows that hold still: a fact, and a heading over a group."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.settings_row import SettingsRow  # noqa: E402


class InfoRow(SettingsRow):
    """Read-only. Still selectable, because on a D-pad a row you cannot
    land on is a row whose end you cannot read — but never `actionable`, so
    the cursor does not *open* on one."""

    def __init__(self, label: str, value: str, *, detail: str = "", icon_name: str = "") -> None:
        super().__init__(label, detail=detail, icon_name=icon_name)
        self.set_value(value, muted=True)
        self.add_css_class("info")

    @property
    def actionable(self) -> bool:
        return False

    @property
    def hint(self) -> str:
        return "Nothing to change on this row"


class GroupRow(SettingsRow):
    """A heading over the rows beneath it.

    Panels here run to fifteen rows — Appearance mixes theme, layout,
    motion, wallpaper and icon caching in one undifferentiated column, of
    which about nine fit on screen. A flat list that long is not a list of
    settings, it is a haystack, and the cheapest fix is to say out loud
    where each group starts.

    It is a `SettingsRow` so `SettingsList` can hold one without a second
    kind of child, and unselectable so every navigation, every scroll
    calculation and every "first row" rule steps over it for free.
    """

    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.add_css_class("group")
        self.set_can_target(False)
        self.set_focusable(False)
        self.update_property([Gtk.AccessibleProperty.LABEL], [title])

    @property
    def selectable(self) -> bool:
        return False

    @property
    def actionable(self) -> bool:
        return False

    def set_scale(self, scale: Scale) -> None:
        """Shorter than a real row, and short enough that a heading costs
        less than the row it is introducing."""
        super().set_scale(scale)
        self.set_size_request(-1, scale.px(46.0))
