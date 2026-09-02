# SPDX-License-Identifier: GPL-3.0-or-later
"""Settings guidance on the left and compact key groups on the right."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.ui.legend import Hint, Legend  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class SettingsFooter(Gtk.Box):
    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self._keys = Legend(scale)
        self._keys.set_halign(Gtk.Align.END)
        self._keys.set_hexpand(True)
        self.append(self._keys)
        self.set_scale(scale)

    def set_label(self, _text: str) -> None:
        pass

    def set_hints(self, hints: tuple[Hint, ...]) -> None:
        self._keys.set_hints(hints)

    def set_input_device(self, source: str, family: str) -> None:
        self._keys.set_input_device(source, family)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(24.0))
        self._keys.set_scale(scale)
