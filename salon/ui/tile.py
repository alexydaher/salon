"""Minimal proof-of-concept tile widget.

The real tile — custom Gtk.Widget with a spring-driven Gsk.Transform scale
and bloom (M3 in the plan) — is the fiddliest, most important piece of the
visual system and deserves its own pass. This stand-in swaps a CSS class on
focus so navigation is visible and testable today.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk  # noqa: E402

from salon.core.model import Tile  # noqa: E402


class TileWidget(Gtk.Box):
    def __init__(self, tile: Tile) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.tile = tile
        self.add_css_class("salon-tile")
        self.set_size_request(280, 160)

        icon = Gtk.Image.new_from_icon_name(tile.icon_name or "application-x-executable-symbolic")
        icon.set_pixel_size(48)
        icon.set_vexpand(True)
        icon.set_valign(Gtk.Align.CENTER)
        self.append(icon)

        label = Gtk.Label(label=tile.title)
        label.add_css_class("salon-tile-title")
        self.append(label)

    def set_focused(self, focused: bool) -> None:
        if focused:
            self.add_css_class("focused")
        else:
            self.remove_css_class("focused")
