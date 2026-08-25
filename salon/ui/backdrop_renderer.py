# SPDX-License-Identifier: GPL-3.0-or-later
"""Rendering collaborator for the ambient home-screen backdrop."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Gdk, Graphene, Gsk, Gtk  # noqa: E402

from salon.ui import theme  # noqa: E402


@dataclass(frozen=True, slots=True)
class Blurred:
    """One prepared layer and whether it should cover the full backdrop."""

    texture: Gdk.Texture
    full_bleed: bool
# stops reading as light and starts reading as the display being tinted —
# which is exactly what the earlier full-screen accent wash got wrong.
_GLOW_ALPHA = 0.13
_GLOW_RADIUS_FRACTION = 0.40

# The blurred artwork is rendered once at this width. Small enough that the
# blur is free, large enough that a logo on a plain field still reads as a
# shape rather than as a smear.
_BLUR_WIDTH = 96
_BLUR_RADIUS = 6.0

# How much of a full-bleed image survives. §7.4 says ~12% luminance: the
# backdrop has to be felt rather than looked at, and every tile label on
# screen is drawn over it. Expressed as one scrim over a fully-drawn image
# rather than as two multiplied alphas, so the number means what it says.
_SCRIM_ALPHA = 0.86

# An icon is not a photograph, and treating it as one gives a black screen:
# a 64px favicon is transparent everywhere except the mark, so cover-fitting
# it across a television leaves almost nothing behind. Icons light the same
# bounded pool the accent does instead — the difference is that the pool now
# has the icon's own colours in it rather than one flat hue. Brighter than
# _GLOW_ALPHA because most of what is being drawn is transparent.
_ICON_POOL_ALPHA = 0.34
_ICON_POOL_RADIUS_FRACTION = 0.55

_WALLPAPER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".avif")

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
    def __init__(self, owner: object) -> None:
        self._owner = owner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._owner, name)

    def blurred(self, source: Gdk.Paintable) -> Gdk.Texture | None:
        """The one expensive step, taken once per artwork and then cached.

        Takes a paintable rather than a texture so an ordinary application
        icon works too. Most tiles on a real home screen are level 4 — an
        icon on a generated card, no photograph anywhere — and if only real
        artwork lit the backdrop, the backdrop would stay dark on almost
        every machine.

        Keyed on identity rather than pixels: the artwork resolver already
        caches decoded textures and icon lookups, so the same tile hands
        back the same object every time and moving back and forth along a
        row re-blurs nothing.
        """
        key = id(source)
        cached = self._blur_cache.get(key)
        if cached is not None:
            return cached[1]
        native = self.get_native()
        renderer = native.get_renderer() if native is not None else None
        if renderer is None:
            # Before realization there is nothing to render with. Returning
            # None here costs one frame of accent-only backdrop; the next
            # focus change fills it in.
            return None
        source_width = float(source.get_intrinsic_width())
        source_height = float(source.get_intrinsic_height())
        if source_width <= 0 or source_height <= 0:
            return None
        width = float(_BLUR_WIDTH)
        height = max(1.0, width * source_height / source_width)
        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)
        snapshot = Gtk.Snapshot()
        snapshot.push_blur(_BLUR_RADIUS)
        source.snapshot(snapshot, width, height)
        snapshot.pop()
        node = snapshot.to_node()
        if node is None:
            return None
        rendered = renderer.render_texture(node, bounds)
        # Bounded: a catalogue of two hundred tiles would otherwise keep two
        # hundred textures alive for a backdrop that shows one at a time.
        if len(self._blur_cache) >= 32:
            self._blur_cache.clear()
        self._blur_cache[key] = (source, rendered)
        return rendered
    def snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0:
            return

        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)

        # Not pure black (§7.2): #000 makes UI edges harsh against a TV's
        # own black level and exaggerates near-black banding on OLED.
        snapshot.append_color(theme.color("surface-0"), bounds)

        if self._wallpaper is not None and self._wallpaper_dim < 1.0:
            self.snapshot_art(snapshot, bounds, self._wallpaper, 1.0)
            surface = theme.color("surface-0")
            snapshot.append_color(
                rgba(surface.red, surface.green, surface.blue, self._wallpaper_dim), bounds
            )

        # Real artwork, under everything else. Both sides of the cross-fade
        # are drawn when one is in progress; outside a fade one of them is
        # None and this is a single upscale.
        fading_out = 1.0 - self._progress
        drew_full_bleed = False
        for art, alpha in ((self._from_art, fading_out), (self._to_art, self._progress)):
            if art is None or alpha <= 0.0 or not art.full_bleed:
                continue
            self.snapshot_art(snapshot, bounds, art.texture, alpha)
            drew_full_bleed = True
        if drew_full_bleed:
            # Down to §7.4's ~12% luminance. Without this the tile titles
            # sit on an unpredictable field and the screen stops being dark.
            surface = theme.color("surface-0")
            snapshot.append_color(
                rgba(surface.red, surface.green, surface.blue, _SCRIM_ALPHA), bounds
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

        # An icon-derived pool goes over the accent gradient, in the same
        # place and with the same feathered edge, so the light behind the
        # focused tile carries that tile's own colours.
        for art, alpha in ((self._from_art, fading_out), (self._to_art, self._progress)):
            if art is None or alpha <= 0.0 or art.full_bleed:
                continue
            self.snapshot_icon_pool(snapshot, bounds, center, art.texture, alpha)

    def snapshot_icon_pool(
        self,
        snapshot: Gtk.Snapshot,
        bounds: Graphene.Rect,
        center: Graphene.Point,
        texture: Gdk.Texture,
        alpha: float,
    ) -> None:
        """The blurred icon, masked to the same bounded pool the accent
        draws — light on a wall, not a tint over the whole display. The
        earlier full-screen accent wash is exactly what this must not
        become."""
        radius = max(bounds.get_width(), bounds.get_height()) * _ICON_POOL_RADIUS_FRACTION
        snapshot.push_mask(Gsk.MaskMode.ALPHA)
        opaque = Gsk.ColorStop()
        opaque.offset = 0.0
        opaque.color = rgba(1.0, 1.0, 1.0, 1.0)
        midway = Gsk.ColorStop()
        midway.offset = 0.5
        midway.color = rgba(1.0, 1.0, 1.0, 0.45)
        clear = Gsk.ColorStop()
        clear.offset = 1.0
        clear.color = _TRANSPARENT
        snapshot.append_radial_gradient(
            bounds, center, radius, radius, 0.0, 1.0, [opaque, midway, clear]
        )
        snapshot.pop()
        self.snapshot_art(snapshot, bounds, texture, alpha * _ICON_POOL_ALPHA)
        snapshot.pop()

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
        # LINEAR, not TRILINEAR: there are no mipmaps worth sampling on a
        # 96px source and the smooth interpolation is the point.
        snapshot.append_scaled_texture(texture, Gsk.ScalingFilter.LINEAR, rect)
        snapshot.pop()
