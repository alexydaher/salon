# SPDX-License-Identifier: GPL-3.0-or-later
"""Icon/title/subtitle header used by item OPTIONS menus."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango  # noqa: E402


class SystemMenuHeader(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("salon-system-menu-header")
        self._icon = Gtk.Image()
        self.append(self._icon)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text.set_hexpand(True)
        self.append(text)
        self._title = Gtk.Label()
        self._title.add_css_class("salon-system-menu-title")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        self._title.set_max_width_chars(32)
        text.append(self._title)
        self._subtitle = Gtk.Label()
        self._subtitle.add_css_class("salon-settings-detail")
        self._subtitle.set_halign(Gtk.Align.START)
        self._subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        self._subtitle.set_max_width_chars(44)
        text.append(self._subtitle)

    def set_content(self, title: str, subtitle: str = "", icon_name: str = "") -> None:
        self._title.set_label(title)
        self._subtitle.set_label(subtitle)
        self._subtitle.set_visible(bool(subtitle))
        self._icon.set_from_icon_name(icon_name or "application-x-executable-symbolic")
        self._icon.set_visible(bool(icon_name or subtitle))
        self.set_visible(bool(title))

    def set_scale(self, scale) -> None:
        self.set_spacing(scale.px(18.0))
        self._icon.set_pixel_size(scale.px(56.0))
