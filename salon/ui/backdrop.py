# SPDX-License-Identifier: GPL-3.0-or-later
"""The ambient backdrop behind the tiles (§7.4).

§7.4's backdrop is the focused tile's artwork, heavily blurred and darkened
to ~12% luminance. Salon has no pre-blur step for that yet, and §7.3 is
explicit that a full-screen blur must never be recomputed per frame on the
weak HTPC GPUs this targets — so rather than blurring a large image every
frame, this draws the *result* that treatment is reaching for: a deep
blue-black field with a single soft pool of the focused tile's colour
behind roughly where that tile sits, as though the lamp in §7.1 lights the
wall behind it too.

That keeps the room-lit feel and the 220ms cross-fade of the real thing at
a fraction of the cost, and it stays correct once artwork blurring lands —
the accent pool becomes the glow *under* the blurred image rather than
being replaced by it.

An earlier version filled the whole screen with the accent colour at 12%
luminance. On a tile with a saturated accent (GeForce NOW's #76B900) that
reads as the screen being tinted green rather than as ambient light, which
is why the colour is now a bounded, heavily-feathered pool instead of a
flat wash.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")

from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui import theme  # noqa: E402

_FADE_MS = 220
# Fast scrolling must not thrash the cross-fade (§7.4).
_DEBOUNCE_MS = 150

# Deliberately restrained. This is meant to read as light falling on a wall
# behind the focused tile, and the moment it covers most of the screen it
# stops reading as light and starts reading as the display being tinted —
# which is exactly what the earlier full-screen accent wash got wrong.
_GLOW_ALPHA = 0.13
_GLOW_RADIUS_FRACTION = 0.40


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


_SURFACE_0 = _parse(tokens.color("surface-0"))
_TRANSPARENT = _rgba(0.0, 0.0, 0.0, 0.0)


class Backdrop(Gtk.Widget):
    def __init__(self) -> None:
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_can_target(False)

        self._from = theme.accent()
        self._to = theme.accent()
        self._progress = 1.0
        # Where the pool of light sits, in 0..1 of the widget's own size —
        # tracks the focused tile so the glow moves with it.
        self._focus_x = 0.25
        self._focus_y = 0.42
        self._pending: Gdk.RGBA | None = None
        self._debounce_id: int | None = None

        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.TimedAnimation.new(self, 0.0, 1.0, _FADE_MS, target)
        self._animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)

    def set_focus_position(self, x: float, y: float) -> None:
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        if (x, y) == (self._focus_x, self._focus_y):
            return
        self._focus_x = x
        self._focus_y = y
        self.queue_draw()

    def set_accent(self, color: Gdk.RGBA | None) -> None:
        """Debounced by 150ms (§7.4): holding a direction to scroll across a
        row fires this once per tile, and cross-fading to every one of them
        in turn both looks like a strobe and wastes the animation."""
        target = color or theme.accent()
        if _same(target, self._to) and self._pending is None:
            return
        self._pending = target
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
        self._debounce_id = GLib.timeout_add(_DEBOUNCE_MS, self._apply_pending)

    def _apply_pending(self) -> bool:
        self._debounce_id = None
        target = self._pending
        self._pending = None
        if target is None or _same(target, self._to):
            return GLib.SOURCE_REMOVE
        self._from = self._current()
        self._to = target
        self._animation.reset()
        self._animation.play()
        return GLib.SOURCE_REMOVE

    def _current(self) -> Gdk.RGBA:
        t = self._progress
        return _rgba(
            self._from.red + (self._to.red - self._from.red) * t,
            self._from.green + (self._to.green - self._from.green) * t,
            self._from.blue + (self._to.blue - self._from.blue) * t,
        )

    def _on_tick(self, value: float) -> None:
        self._progress = value
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0:
            return

        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)

        # Not pure black (§7.2): #000 makes UI edges harsh against a TV's
        # own black level and exaggerates near-black banding on OLED.
        snapshot.append_color(_SURFACE_0, bounds)

        accent = self._current()
        center = Graphene.Point()
        center.init(width * self._focus_x, height * self._focus_y)
        radius = max(width, height) * _GLOW_RADIUS_FRACTION

        inner = Gsk.ColorStop()
        inner.offset = 0.0
        inner.color = _rgba(accent.red, accent.green, accent.blue, _GLOW_ALPHA)
        mid = Gsk.ColorStop()
        mid.offset = 0.45
        mid.color = _rgba(accent.red, accent.green, accent.blue, _GLOW_ALPHA * 0.35)
        outer = Gsk.ColorStop()
        outer.offset = 1.0
        outer.color = _TRANSPARENT

        snapshot.append_radial_gradient(
            bounds, center, radius, radius, 0.0, 1.0, [inner, mid, outer]
        )


def _same(a: Gdk.RGBA, b: Gdk.RGBA) -> bool:
    return (a.red, a.green, a.blue) == (b.red, b.green, b.blue)
