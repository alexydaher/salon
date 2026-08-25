# SPDX-License-Identifier: GPL-3.0-or-later
"""Backdrop state, wallpaper selection, and focus transitions."""

from __future__ import annotations

import os
import random
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from salon.ui import motion, theme  # noqa: E402
from salon.ui.backdrop_renderer import (  # noqa: E402
    BackdropRenderer,
    Blurred,
    rgba,
    same_color,
)

_FADE_MS = 280
_DEBOUNCE_MS = 80
_WALLPAPER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".avif")
_DEFAULT_WALLPAPER = "resource:///io/github/alexydaher/Salon/backgrounds/salon-ambient.png"
_DEFAULT_WALLPAPER_DIM = 0.38


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

        # The blurred artwork, cross-fading on the same clock as the accent
        # so the colour and the picture never disagree about which tile the
        # cursor is on.
        self._from_art: Blurred | None = None
        self._to_art: Blurred | None = None
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
        # Empty is the designed Salon ambience. A single dash is the
        # deliberate opt-out for people who want the palette's flat surface.
        effective_source = _DEFAULT_WALLPAPER if not source else source
        if source == "-":
            effective_source = ""
        self._wallpaper_dim = (
            _DEFAULT_WALLPAPER_DIM if not source else max(0.0, min(1.0, dim))
        )
        if effective_source != self._wallpaper_source:
            self._wallpaper_source = effective_source
            self._wallpaper = self._load(effective_source)
        self.queue_draw()

    def next_wallpaper(self) -> None:
        if self._wallpaper_source:
            self._wallpaper = self._load(self._wallpaper_source)
            self.queue_draw()

    def _load(self, source: str) -> Gdk.Texture | None:
        if not source:
            return None
        if source.startswith("resource://"):
            try:
                return Gdk.Texture.new_from_resource(source.removeprefix("resource://"))
            except GLib.Error:
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
        unchanged = same_color(target, self._to) and artwork == self._source_art
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
        if same_color(target, self._to) and source == self._source_art:
            return GLib.SOURCE_REMOVE
        self._from = self._current()
        self._to = target
        self._source_art = source
        self._from_art = self._to_art
        self._to_art = None
        if source is not None:
            paintable, full_bleed = source
            blurred = self.blurred(paintable)
            if blurred is not None:
                self._to_art = Blurred(texture=blurred, full_bleed=full_bleed)
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
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        BackdropRenderer.snapshot(self, snapshot)
