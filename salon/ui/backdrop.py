# SPDX-License-Identifier: GPL-3.0-or-later
"""Backdrop state, wallpaper selection, and focus transitions."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")

from gi.repository import Adw, Gdk, GLib, Graphene, Gsk, Gtk  # noqa: E402

from salon.ui import backdrop_wallpaper, motion, theme  # noqa: E402
from salon.ui.backdrop_renderer import BackdropRenderer, rgba, same_color  # noqa: E402

_FADE_MS = 280
_DEBOUNCE_MS = 80
# The ambient layers are rendered into a texture this many times smaller
# than the widget and blitted back up. Four, because the wallpaper is
# 1672px wide and already being upscaled on any television — a quarter of a
# 5K screen is 1280px, which is still more than the source has to give —
# while the rest of what this draws is a flat fill, a dim and one very wide
# radial gradient, none of which carry detail a quarter-resolution copy
# could lose.
_TEXTURE_DIVISOR = 4
# The tint is quantised before it becomes part of the texture's identity,
# so a 280ms cross-fade re-renders the small texture a dozen times rather
# than on all seventeen frames. Two per cent of the colour range is far
# below what is visible through a backdrop this dim.
_TINT_STEPS = 50


class Backdrop(Gtk.Widget, BackdropRenderer):
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

        self._wallpaper: Gdk.Texture | None = None
        self._wallpaper_dim = 0.72
        self._wallpaper_source = ""

        # The composed ambient layers, rendered small and blitted back up.
        # See `_refresh_texture`.
        self._texture: Gdk.Texture | None = None
        self._texture_key: tuple[object, ...] | None = None
        # Counted rather than compared: a slideshow's next picture arrives
        # under the same source string, and identity is not a safe key for
        # an object the previous one has just been freed to make room for.
        self._wallpaper_serial = 0

        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.TimedAnimation.new(self, 0.0, 1.0, _FADE_MS, target)
        self._animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)

    # --- wallpaper -------------------------------------------------------

    def set_wallpaper(self, source: str, dim: float) -> None:
        """A file, a folder to pick from, or "" for none.

        `backdrop_wallpaper` owns what the string means; a folder is a
        slideshow and `next_wallpaper` is what advances it.
        """
        effective_source = backdrop_wallpaper.resolve_source(source)
        self._wallpaper_dim = backdrop_wallpaper.resolve_dim(source, dim)
        if effective_source != self._wallpaper_source:
            self._wallpaper_source = effective_source
            self._set_wallpaper_texture(backdrop_wallpaper.load(effective_source))
        self._refresh_texture()
        self.queue_draw()

    def next_wallpaper(self) -> None:
        if self._wallpaper_source:
            self._set_wallpaper_texture(backdrop_wallpaper.load(self._wallpaper_source))
            self._refresh_texture()
            self.queue_draw()

    def _set_wallpaper_texture(self, texture: Gdk.Texture | None) -> None:
        self._wallpaper = texture
        self._wallpaper_serial += 1

    def set_focus_position(self, x: float, y: float) -> None:
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        if (x, y) == (self._focus_x, self._focus_y):
            return
        self._focus_x = x
        self._focus_y = y
        self._refresh_texture()
        self.queue_draw()

    def set_focus(self, color: Gdk.RGBA | None) -> None:
        """Change the wallpaper tint to the colour under the cursor.

        Debounced by 80ms: holding a direction to scroll across a
        row fires this once per tile, and cross-fading to every one of them
        in turn looks like a strobe.
        """
        target = color or theme.accent()
        if same_color(target, self._to) and self._pending is None:
            return
        self._pending = target
        if self._debounce_id is not None:
            GLib.source_remove(self._debounce_id)
        self._debounce_id = GLib.timeout_add(_DEBOUNCE_MS, self._apply_pending)

    def set_accent(self, color: Gdk.RGBA | None) -> None:
        """Colour only, for callers with no artwork to offer."""
        self.set_focus(color)

    def _apply_pending(self) -> bool:
        self._debounce_id = None
        target = self._pending
        self._pending = None
        if target is None:
            return GLib.SOURCE_REMOVE
        if same_color(target, self._to):
            return GLib.SOURCE_REMOVE
        self._from = self._current()
        self._to = target
        self._animation.set_duration(motion.duration_ms(_FADE_MS))
        self._animation.reset()
        self._animation.play()
        return GLib.SOURCE_REMOVE

    def _current(self) -> Gdk.RGBA:
        t = self._progress
        return rgba(
            self._from.red + (self._to.red - self._from.red) * t,
            self._from.green + (self._to.green - self._from.green) * t,
            self._from.blue + (self._to.blue - self._from.blue) * t,
        )

    def _on_tick(self, value: float) -> None:
        self._progress = value
        self._refresh_texture()
        self.queue_draw()

    # --- the composed texture --------------------------------------------

    def _texture_key_now(self) -> tuple[object, ...]:
        """Everything the ambient layers are a function of."""
        accent = self._current()
        return (
            self.get_width(),
            self.get_height(),
            self._wallpaper_source,
            self._wallpaper_serial,
            round(self._wallpaper_dim, 3),
            round(accent.red * _TINT_STEPS),
            round(accent.green * _TINT_STEPS),
            round(accent.blue * _TINT_STEPS),
            round(self._focus_x, 4),
            round(self._focus_y, 4),
        )

    def _refresh_texture(self) -> None:
        """Re-render the ambient layers into a small texture, if anything
        they depend on has changed.

        Called from the setters and from the cross-fade's own tick — never
        from `do_snapshot`, because this asks the window's renderer to
        render, and doing that from inside a snapshot would re-enter the
        renderer that is already running.
        """
        width = self.get_width()
        height = self.get_height()
        if width <= 0 or height <= 0:
            return
        key = self._texture_key_now()
        if key == self._texture_key:
            return
        native = self.get_native()
        renderer = native.get_renderer() if native is not None else None
        if renderer is None:
            # Before the window is realized there is nothing to render
            # with; do_snapshot paints the layers directly until there is.
            return

        small_width = max(1, width // _TEXTURE_DIVISOR)
        small_height = max(1, height // _TEXTURE_DIVISOR)
        snapshot = Gtk.Snapshot()
        self.snapshot_layers(snapshot, float(small_width), float(small_height))
        node = snapshot.to_node()
        if node is None:
            return
        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, float(small_width), float(small_height))
        self._texture = renderer.render_texture(node, bounds)
        self._texture_key = key

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        Gtk.Widget.do_size_allocate(self, width, height, baseline)
        self._refresh_texture()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if self._texture is not None and self._texture_key == self._texture_key_now():
            bounds = Graphene.Rect()
            bounds.init(0.0, 0.0, width, height)
            snapshot.append_scaled_texture(self._texture, Gsk.ScalingFilter.LINEAR, bounds)
            return
        # No texture yet (or it is a frame out of date): draw the real
        # thing. Correct either way — the texture is an optimisation, not a
        # different picture.
        BackdropRenderer.snapshot(self, snapshot)
