# SPDX-License-Identifier: GPL-3.0-or-later
"""The 206du live-preview strip and its fixed metadata hierarchy."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from salon.ui.legend import Hint, Legend  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.settings.settings_row import SettingsRow  # noqa: E402


class PreviewStrip(Gtk.Box):
    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("salon-settings-preview-bar")
        self.set_visible(False)
        self.set_valign(Gtk.Align.END)
        self.set_vexpand(True)
        self._main = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._main.set_vexpand(True)
        self.append(self._main)
        self._meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._main.append(self._meta)
        self._title = Gtk.Label()
        self._title.add_css_class("salon-preview-title")
        self._title.set_halign(Gtk.Align.START)
        self._meta.append(self._title)
        self.choices = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.choices.set_hexpand(True)
        self.choices.set_homogeneous(True)
        self._main.append(self.choices)
        self._footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(self._footer)
        self._controls = Legend(scale)
        self._controls.set_halign(Gtk.Align.END)
        self._controls.set_hexpand(True)
        self._footer.append(self._controls)
        self.set_scale(scale)

    def set_row(self, row: SettingsRow) -> None:
        self._title.set_label(row.label_text)

    def set_controls(self, hints: tuple[Hint, ...]) -> None:
        self._controls.set_hints(hints)

    def set_input_device(self, source: str, family: str) -> None:
        self._controls.set_input_device(source, family)

    def set_scale(self, scale: Scale) -> None:
        self.set_size_request(-1, scale.px(206.0))
        self._main.set_spacing(scale.px(44.0))
        self._main.set_margin_start(scale.px(48.0))
        self._main.set_margin_end(scale.px(48.0))
        self._main.set_margin_top(scale.px(24.0))
        self._meta.set_size_request(scale.px(300.0), -1)
        self._meta.set_hexpand(False)
        self._meta.set_halign(Gtk.Align.START)
        self._meta.set_spacing(scale.px(5.0))
        self.choices.set_spacing(scale.px(14.0))
        self._footer.set_margin_start(scale.px(48.0))
        self._footer.set_margin_end(scale.px(48.0))
        self._footer.set_margin_bottom(scale.px(7.0))
        self._controls.set_scale(scale)
        self._controls.set_margin_end(0)
        self._controls.set_margin_bottom(0)
