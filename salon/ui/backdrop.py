# SPDX-License-Identifier: GPL-3.0-or-later
"""The ambient backdrop behind the tiles (§7.4).

§7.4 asks for the focused tile's artwork, heavily blurred and darkened to
around 12% luminance, cross-fading over 220ms. This does exactly that now,
and the accent pool it used to draw on its own has become the glow
*underneath* the image rather than a substitute for it.

**The blur is computed once per focus change, never per frame.** §7.3 is
explicit that a full-screen blur must not be recomputed every frame on the
weak HTPC GPUs this targets, and it would be: at 4K that is eight million
pixels through a separable Gaussian sixty times a second, for a picture
that only changes when the cursor moves. Instead `_blurred()` renders the
artwork once into a ~96px-wide texture with `push_blur` applied at that
size — a few thousand pixels — and every frame afterwards is a single
bilinear upscale of that small texture, which is the cheapest operation a
GPU has. Upscaling a 96px image to fill a television *is* a blur, and a
very smooth one; the explicit blur at small size only softens the last of
the blockiness.

Downscaling also solves the thing that killed the earlier full-screen
accent wash: a saturated image no longer tints the display, because what
survives a reduction to 96px and a dark scrim is the picture's broad
lighting rather than its colour.

An earlier version filled the whole screen with the accent colour at 12%
luminance. On a tile with a saturated accent (GeForce NOW's #76B900) that
reads as the screen being tinted green rather than as ambient light, which
is why the colour is a bounded, heavily-feathered pool.

Underneath all of it sits the wallpaper, if the user set one — a still
image or a folder of them. It is drawn once at full size and dimmed by
`wallpaper-dim`, not blurred: a wallpaper is a picture somebody chose, and
blurring it would be second-guessing that. It is the layer everything else
is composited over, so the focused tile's light falls on it.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")

from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

from salon.ui import motion, theme  # noqa: E402


@dataclass(frozen=True, slots=True)
class _Blurred:
    """One prepared backdrop layer.

    `full_bleed` records what kind of picture it came from, because the two
    kinds want opposite treatments and the difference is not recoverable
    from the pixels: a poster fills the screen, an icon lights a pool.
    """

    texture: Gdk.Texture
    full_bleed: bool

_FADE_MS = 220
# Fast scrolling must not thrash the cross-fade (§7.4).
_DEBOUNCE_MS = 150

# Deliberately restrained. This is meant to read as light falling on a wall
# behind the focused tile, and the moment it covers most of the screen it
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

        # The blurred artwork, cross-fading on the same clock as the accent
        # so the colour and the picture never disagree about which tile the
        # cursor is on.
        self._from_art: _Blurred | None = None
        self._to_art: _Blurred | None = None
        self._pending_art: tuple[Gdk.Paintable, bool] | None = None
        self._source_art: tuple[Gdk.Paintable, bool] | None = None
        # Keyed by the source paintable's identity, and holding a
        # reference to that source as well as the blur: without pinning it,
        # a freed source could have its id reused by a different paintable
        # and hand back the wrong backdrop.
        self._blur_cache: dict[int, tuple[Gdk.Paintable, Gdk.Texture]] = {}

        self._wallpaper: Gdk.Texture | None = None
        self._wallpaper_dim = 0.72
        self._wallpaper_source = ""

        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.TimedAnimation.new(self, 0.0, 1.0, _FADE_MS, target)
        self._animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)

    # --- wallpaper -------------------------------------------------------

    def set_wallpaper(self, source: str, dim: float) -> None:
        """A file, a folder to pick from, or "" for none.

        A folder is a slideshow: one image is chosen at random per call,
        and `next_wallpaper` is what advances it. Random rather than
        alphabetical because a slideshow that always opens on the same
        picture is not one.
        """
        self._wallpaper_dim = max(0.0, min(1.0, dim))
        if source != self._wallpaper_source:
            self._wallpaper_source = source
            self._wallpaper = self._load(source)
        self.queue_draw()

    def next_wallpaper(self) -> None:
        if self._wallpaper_source:
            self._wallpaper = self._load(self._wallpaper_source)
            self.queue_draw()

    def _load(self, source: str) -> Gdk.Texture | None:
        if not source:
            return None
        path = Path(os.path.expanduser(source))
        if path.is_dir():
            try:
                candidates = sorted(
                    entry
                    for entry in path.iterdir()
                    if entry.suffix.lower() in _WALLPAPER_SUFFIXES and entry.is_file()
                )
            except OSError:
                return None
            if not candidates:
                return None
            path = random.choice(candidates)
        if not path.is_file():
            return None
        try:
            return Gdk.Texture.new_from_filename(str(path))
        except GLib.Error:
            # A file that is not an image, or one being written to right
            # now. The palette's own surface colour is a correct backdrop.
            return None

    def set_focus_position(self, x: float, y: float) -> None:
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        if (x, y) == (self._focus_x, self._focus_y):
            return
        self._focus_x = x
        self._focus_y = y
        self.queue_draw()

    def set_focus(
        self, color: Gdk.RGBA | None, artwork: tuple[Gdk.Paintable, bool] | None = None
    ) -> None:
        """What the cursor is now on: its colour, and its picture if it has
        one.

        Debounced by 150ms (§7.4): holding a direction to scroll across a
        row fires this once per tile, and cross-fading to every one of them
        in turn both looks like a strobe and wastes the animation. The blur
        is on the far side of the debounce too, so a held direction never
        renders one.
        """
        target = color or theme.accent()
        unchanged = _same(target, self._to) and artwork == self._source_art
        if unchanged and self._pending is None:
            return
        self._pending = target
        self._pending_art = artwork
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
        self._debounce_id = GLib.timeout_add(_DEBOUNCE_MS, self._apply_pending)

    def set_accent(self, color: Gdk.RGBA | None) -> None:
        """Colour only, for callers with no artwork to offer."""
        self.set_focus(color, None)

    def _apply_pending(self) -> bool:
        self._debounce_id = None
        target = self._pending
        source = self._pending_art
        self._pending = None
        self._pending_art = None
        if target is None:
            return GLib.SOURCE_REMOVE
        if _same(target, self._to) and source == self._source_art:
            return GLib.SOURCE_REMOVE
        self._from = self._current()
        self._to = target
        self._source_art = source
        self._from_art = self._to_art
        self._to_art = None
        if source is not None:
            paintable, full_bleed = source
            blurred = self._blurred(paintable)
            if blurred is not None:
                self._to_art = _Blurred(texture=blurred, full_bleed=full_bleed)
        self._animation.set_duration(motion.duration_ms(_FADE_MS))
        self._animation.reset()
        self._animation.play()
        return GLib.SOURCE_REMOVE

    def _blurred(self, source: Gdk.Paintable) -> Gdk.Texture | None:
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
        snapshot.append_color(theme.color("surface-0"), bounds)

        if self._wallpaper is not None and self._wallpaper_dim < 1.0:
            self._snapshot_art(snapshot, bounds, self._wallpaper, 1.0)
            surface = theme.color("surface-0")
            snapshot.append_color(
                _rgba(surface.red, surface.green, surface.blue, self._wallpaper_dim), bounds
            )

        # Real artwork, under everything else. Both sides of the cross-fade
        # are drawn when one is in progress; outside a fade one of them is
        # None and this is a single upscale.
        fading_out = 1.0 - self._progress
        drew_full_bleed = False
        for art, alpha in ((self._from_art, fading_out), (self._to_art, self._progress)):
            if art is None or alpha <= 0.0 or not art.full_bleed:
                continue
            self._snapshot_art(snapshot, bounds, art.texture, alpha)
            drew_full_bleed = True
        if drew_full_bleed:
            # Down to §7.4's ~12% luminance. Without this the tile titles
            # sit on an unpredictable field and the screen stops being dark.
            surface = theme.color("surface-0")
            snapshot.append_color(
                _rgba(surface.red, surface.green, surface.blue, _SCRIM_ALPHA), bounds
            )

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

        # An icon-derived pool goes over the accent gradient, in the same
        # place and with the same feathered edge, so the light behind the
        # focused tile carries that tile's own colours.
        for art, alpha in ((self._from_art, fading_out), (self._to_art, self._progress)):
            if art is None or alpha <= 0.0 or art.full_bleed:
                continue
            self._snapshot_icon_pool(snapshot, bounds, center, art.texture, alpha)

    def _snapshot_icon_pool(
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
        opaque.color = _rgba(1.0, 1.0, 1.0, 1.0)
        midway = Gsk.ColorStop()
        midway.offset = 0.5
        midway.color = _rgba(1.0, 1.0, 1.0, 0.45)
        clear = Gsk.ColorStop()
        clear.offset = 1.0
        clear.color = _TRANSPARENT
        snapshot.append_radial_gradient(
            bounds, center, radius, radius, 0.0, 1.0, [opaque, midway, clear]
        )
        snapshot.pop()
        self._snapshot_art(snapshot, bounds, texture, alpha * _ICON_POOL_ALPHA)
        snapshot.pop()

    def _snapshot_art(
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


def _same(a: Gdk.RGBA, b: Gdk.RGBA) -> bool:
    return (a.red, a.green, a.blue) == (b.red, b.green, b.blue)
