# SPDX-License-Identifier: GPL-3.0-or-later
"""Rendering collaborator for the ambient home-screen backdrop."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk  # noqa: E402

from salon.ui import theme  # noqa: E402

# Keep the positional glow restrained: the wallpaper now carries the accent
# across the display, while this layer only shows where focus currently sits.
_GLOW_ALPHA = 0.13
_GLOW_RADIUS_FRACTION = 0.40

# The final visual direction uses several broad pools of colour rather than
# one spotlight. They are deliberately cheap GSK gradients rendered into the
# Backdrop's quarter-resolution cache, not live blurred widgets.
_AMBIENT_FIELDS = (
    (0.02, 0.02, 0.58, 0.20, "#176DDB", 0.34),
    (0.50, 0.54, 0.52, 0.22, "#D57A2D", 0.22),
    (0.96, 0.12, 0.54, 0.22, "#6638B8", 0.25),
    (0.82, 0.92, 0.48, 0.22, "#0A9D9B", 0.18),
)


def rgba(red: float, green: float, blue: float, alpha: float = 1.0) -> Gdk.RGBA:
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


_TRANSPARENT = rgba(0.0, 0.0, 0.0, 0.0)


def same_color(a: Gdk.RGBA, b: Gdk.RGBA) -> bool:
    return (a.red, a.green, a.blue) == (b.red, b.green, b.blue)


class BackdropRenderer:
    def snapshot(self, snapshot: Gtk.Snapshot) -> None:
        self.snapshot_layers(snapshot, float(self.get_width()), float(self.get_height()))

    def snapshot_layers(self, snapshot: Gtk.Snapshot, width: float, height: float) -> None:
        """Paint the ambient layers into a box of the given size.

        Sized by the caller rather than by `get_width()`/`get_height()`
        because `Backdrop` renders this into a reduced-resolution texture
        and blits that instead of painting it live: this is five or six
        full-screen passes — a fill, a cover-fitted photo, both halves of a
        `COLOR` blend, the dim and the glow — and on a 5K display that alone
        was costing about fifteen milliseconds of every frame while the rows
        were moving underneath it. Nothing here reads the widget's own size,
        so the same code draws the cheap small copy and the full-size
        fallback.
        """
        if width <= 0 or height <= 0:
            return

        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)

        # Not pure black (§7.2): #000 makes UI edges harsh against a TV's
        # own black level and exaggerates near-black banding on OLED.
        snapshot.append_color(theme.color("surface-0"), bounds)

        if self._wallpaper is not None and self._wallpaper_dim < 1.0:
            # COLOR takes hue and saturation from the focused app's accent,
            # but luminosity from the wallpaper. The photo therefore keeps
            # all of its texture and lighting while visibly belonging to the
            # app under the cursor; no app logo is painted into the backdrop.
            snapshot.push_blend(Gsk.BlendMode.COLOR)
            self.snapshot_art(snapshot, bounds, self._wallpaper, 1.0)
            snapshot.pop()
            snapshot.append_color(self._current(), bounds)
            snapshot.pop()
            surface = theme.color("surface-0")
            snapshot.append_color(
                rgba(surface.red, surface.green, surface.blue, self._wallpaper_dim), bounds
            )

        for x, y, radius_x, radius_y, value, alpha in _AMBIENT_FIELDS:
            self._snapshot_ambient_field(
                snapshot, bounds, x, y, radius_x, radius_y, _parse(value), alpha
            )

        accent = self._current()
        center = Graphene.Point()
        center.init(width * self._focus_x, height * self._focus_y)
        radius = max(width, height) * _GLOW_RADIUS_FRACTION

        inner = Gsk.ColorStop()
        inner.offset = 0.0
        inner.color = rgba(accent.red, accent.green, accent.blue, _GLOW_ALPHA)
        mid = Gsk.ColorStop()
        mid.offset = 0.45
        mid.color = rgba(accent.red, accent.green, accent.blue, _GLOW_ALPHA * 0.35)
        outer = Gsk.ColorStop()
        outer.offset = 1.0
        outer.color = _TRANSPARENT

        snapshot.append_radial_gradient(
            bounds, center, radius, radius, 0.0, 1.0, [inner, mid, outer]
        )

        # A dark veil keeps type and QR edges stable over every combination
        # of ambient fields and user wallpaper.
        snapshot.append_color(rgba(0.02, 0.03, 0.05, 0.34), bounds)

    @staticmethod
    def _snapshot_ambient_field(
        snapshot: Gtk.Snapshot,
        bounds: Graphene.Rect,
        x: float,
        y: float,
        radius_x: float,
        radius_y: float,
        color: Gdk.RGBA,
        alpha: float,
    ) -> None:
        center = Graphene.Point()
        center.init(bounds.get_width() * x, bounds.get_height() * y)
        inner = Gsk.ColorStop()
        inner.offset = 0.0
        inner.color = rgba(color.red, color.green, color.blue, alpha)
        outer = Gsk.ColorStop()
        outer.offset = 1.0
        outer.color = _TRANSPARENT
        snapshot.append_radial_gradient(
            bounds,
            center,
            bounds.get_width() * radius_x,
            bounds.get_height() * radius_y,
            0.0,
            1.0,
            [inner, outer],
        )

    def snapshot_art(
        self, snapshot: Gtk.Snapshot, bounds: Graphene.Rect, texture: Gdk.Texture, alpha: float
    ) -> None:
        """Cover-fit and never letterbox: a black band down the side of the
        backdrop would read as a broken image rather than as ambience."""
        if alpha <= 0.0:
            return
        width = float(texture.get_width())
        height = float(texture.get_height())
        if width <= 0 or height <= 0:
            return
        scale = max(bounds.get_width() / width, bounds.get_height() / height)
        drawn_width = width * scale
        drawn_height = height * scale
        rect = Graphene.Rect()
        rect.init(
            (bounds.get_width() - drawn_width) / 2.0,
            (bounds.get_height() - drawn_height) / 2.0,
            drawn_width,
            drawn_height,
        )
        snapshot.push_opacity(alpha)
        # LINEAR keeps a cover-fitted wallpaper smooth without inventing
        # detail that is not present in the source.
        snapshot.append_scaled_texture(texture, Gsk.ScalingFilter.LINEAR, rect)
        snapshot.pop()
