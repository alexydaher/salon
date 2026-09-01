# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings guidance on the left and compact key groups on the right."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango  # noqa: E402

from salon.core.bindings import GAMEPAD  # noqa: E402
from salon.ui.legend import Hint, Legend  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class SettingsFooter(Gtk.Box):
    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._guidance = Gtk.Label()
        self._guidance.add_css_class("salon-settings-legend")
        self._guidance.set_halign(Gtk.Align.START)
        self._guidance.set_ellipsize(Pango.EllipsizeMode.END)
        self._guidance.set_hexpand(True)
        self.append(self._guidance)
        self._keys = Legend(scale)
        self.append(self._keys)
        self.set_scale(scale)

    def set_label(self, text: str) -> None:
        self._guidance.set_label(text)

    def set_hints(self, hints: tuple[Hint, ...]) -> None:
        self._keys.set_hints(hints)

    def set_input_device(self, source: str, family: str) -> None:
        self._keys.set_input_device(source, family)
        # Controller guidance belongs in the drawable prompts. Keeping the
        # prose too would leave OK/BACK/MENU words beside their real marks.
        self._guidance.set_visible(source != GAMEPAD)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(24.0))
        self._keys.set_scale(scale)
