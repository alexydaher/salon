# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused full-screen overlay widget."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.core.model import Tile  # noqa: E402
from salon.services.artwork import glow_color  # noqa: E402
from salon.ui import motion, theme  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402


def _rgba(red: float, green: float, blue: float, alpha: float = 1.0) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red = red
    color.green = green
    color.blue = blue
    color.alpha = alpha
    return color


def _parse(value: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(value)
    return color


_ACCENT = _parse(tokens.color("accent"))
_TRANSPARENT = _rgba(0.0, 0.0, 0.0, 0.0)


class _AccentScrim(Gtk.Widget):
    """A near-opaque field with a soft pool of the launching tile's colour
    behind the text — §6.4 asks for a full-bleed overlay built from the
    tile's artwork, and this is the same light-fall treatment the tile and
    backdrop use, so a launch looks like the tile expanding rather than like
    a modal dialog appearing."""

    def __init__(self) -> None:
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self._accent = _ACCENT

    def set_accent(self, accent: Gdk.RGBA | None) -> None:
        # As a light source, not a surface colour — a muted app-icon accent
        # produces no visible pool at all at this alpha (see glow_color).
        self._accent = glow_color(accent) if accent is not None else _ACCENT
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0:
            return
        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)
        surface = theme.color("surface-0")
        scrim = _rgba(surface.red, surface.green, surface.blue, 0.95)
        snapshot.append_color(scrim, bounds)

        center = Graphene.Point()
        center.init(width / 2.0, height * 0.45)
        inner = Gsk.ColorStop()
        inner.offset = 0.0
        inner.color = _rgba(self._accent.red, self._accent.green, self._accent.blue, 0.22)
        outer = Gsk.ColorStop()
        outer.offset = 1.0
        outer.color = _TRANSPARENT
        radius = max(width, height) * 0.45
        snapshot.append_radial_gradient(bounds, center, radius, radius, 0.0, 1.0, [inner, outer])


class LaunchingOverlay(Gtk.Overlay, motion.FadesIn):
    """Absorbs all input until the child window takes focus (or a 12s
    timeout shows a recovery message instead) — that's what prevents a
    second OK press from double-launching while it's up."""

    def __init__(self, scale: Scale) -> None:
        super().__init__()
        self._init_fade()
        self.set_visible(False)
        # Absorb input so a second OK/BACK press can't double-launch or
        # leak through to whatever's behind the overlay while it's up.
        self.set_can_target(True)

        self._scrim = _AccentScrim()
        self.set_child(self._scrim)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content.set_halign(Gtk.Align.CENTER)
        self._content.set_valign(Gtk.Align.CENTER)
        self.add_overlay(self._content)

        self._spinner = Gtk.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._content.append(self._spinner)

        self._title_label = Gtk.Label()
        self._title_label.add_css_class("salon-launching-title")
        self._title_label.set_halign(Gtk.Align.CENTER)
        self._content.append(self._title_label)

        self._message_label = Gtk.Label()
        self._message_label.add_css_class("salon-launching-message")
        self._message_label.set_halign(Gtk.Align.CENTER)
        self._message_label.set_visible(False)
        self._content.append(self._message_label)

        # The way back, said while it can still be read. Once the child has
        # the screen this overlay is behind it and so is every toast Salon
        # can raise — the seconds between OK and the app appearing are the
        # only window in which Salon can tell anyone anything at all.
        self._hint_label = Gtk.Label()
        self._hint_label.add_css_class("salon-launching-message")
        self._hint_label.set_halign(Gtk.Align.CENTER)
        self._content.append(self._hint_label)

        self.set_scale(scale)

    def set_scale(self, scale: Scale) -> None:
        self._content.set_spacing(scale.px(28.0))
        self._spinner.set_size_request(scale.px(64.0), scale.px(64.0))

    def show_for(self, tile: Tile, accent: Gdk.RGBA | None = None, hint: str = "") -> None:
        self._scrim.set_accent(accent)
        self._title_label.set_label(f"Starting {tile.title}…")
        self._message_label.set_visible(False)
        self._hint_label.set_label(hint)
        self._hint_label.set_visible(bool(hint))
        self._spinner.set_spinning(True)
        self.set_visible(True)
        self._begin_fade()

    def show_timed_out(self) -> None:
        self._message_label.set_label(
            "This is taking a while — check that the app started, or press BACK."
        )
        self._message_label.set_visible(True)

    def hide(self) -> None:
        self._spinner.set_spinning(False)
        self.set_visible(False)
