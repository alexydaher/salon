# SPDX-License-Identifier: GPL-3.0-or-later
"""Compact now-playing status kept separate from selected-tile detail."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


class NowPlayingStatus(Gtk.Box):
    def __init__(self, scale: Scale) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.add_css_class("salon-now-playing")
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.END)
        self.set_visible(False)
        self.set_accessible_role(Gtk.AccessibleRole.STATUS)

        self._icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        self.append(self._icon)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.append(labels)
        self._title = Gtk.Label()
        self._title.add_css_class("salon-now-playing-title")
        self._title.set_halign(Gtk.Align.START)
        self._title.set_ellipsize(Pango.EllipsizeMode.END)
        labels.append(self._title)
        self._detail = Gtk.Label()
        self._detail.add_css_class("salon-now-playing-detail")
        self._detail.set_halign(Gtk.Align.START)
        self._detail.set_ellipsize(Pango.EllipsizeMode.END)
        labels.append(self._detail)
        self._labels = labels
        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self.set_spacing(scale.px(12.0))
        self._labels.set_spacing(scale.px(2.0))
        self._icon.set_pixel_size(scale.px(28.0))
        self.set_size_request(scale.px(300.0), -1)
        self.set_margin_end(scale.px(24.0))
        self.set_margin_bottom(scale.px(tokens.BOTTOM_CHROME_MARGIN_DU))

    def set_track(self, title: str, detail: str, *, playing: bool) -> None:
        state = "Playing" if playing else "Paused"
        icon_name = (
            "media-playback-pause-symbolic"
            if playing
            else "media-playback-start-symbolic"
        )
        self._icon.set_from_icon_name(icon_name)
        self._title.set_label(title)
        self._detail.set_label(detail)
        self._detail.set_visible(bool(detail))
        phrase = f"{state} {title}"
        if detail:
            phrase += f", {detail}"
        self.update_property([Gtk.AccessibleProperty.LABEL], [phrase])
        self.set_visible(True)

    def clear(self) -> None:
        self.set_visible(False)
