# SPDX-License-Identifier: GPL-3.0-or-later
"""Opening fades shared by full-screen surfaces."""

from __future__ import annotations

from typing import Protocol

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

from salon.ui.motion_settings import SCREEN_FADE_MS, duration_ms, enabled  # noqa: E402


class FadeIn:
    """Fades a surface up as it opens.

    In only, never out, and that asymmetry is deliberate rather than
    unfinished. Salon routes every press by asking each surface
    `get_visible()` — `_handle_action` does it a dozen times over — so a
    fade-*out* would have to keep a closing screen visible for the length
    of the fade, and every one of those checks would spend that time
    answering for a screen the user has already left: BACK would land on
    the settings screen that is halfway gone. Fading in has no such
    hazard, because the widget is visible and targetable from the first
    frame and only its paint is late.

    This exists because GNOME Kiosk has almost no window animations of its
    own: its compositor fades a window in on map and does nothing at all on
    destroy, minimise, resize or workspace change. Under GNOME Shell those
    transitions come from the Shell; under kiosk, whatever Salon does not
    animate itself simply snaps.
    """

    def __init__(self, widget: Gtk.Widget, base_ms: int = SCREEN_FADE_MS) -> None:
        self._widget = widget
        self._base_ms = base_ms
        self._enabled = True
        self._map_handler: int | None = None
        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.TimedAnimation.new(widget, 0.0, 1.0, base_ms, target)
        self._animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)

    def set_enabled(self, enabled: bool) -> None:
        """Follows the same reduced-motion decision as everything else; see
        `HomeView._animations_enabled`."""
        self._enabled = enabled
        if not enabled:
            self.finish()

    def _on_tick(self, value: float) -> None:
        self._widget.set_opacity(value)

    def play(self) -> None:
        """Call immediately after `set_visible(True)`."""
        if not (self._enabled and enabled()):
            self.finish()
            return
        self._animation.set_duration(duration_ms(self._base_ms))
        # reset() before play() so a surface reopened mid-fade starts from
        # transparent rather than from wherever the last one stopped.
        self._animation.reset()
        self._widget.set_opacity(0.0)
        if self._widget.get_mapped():
            self._animation.play()
            return
        # **The trap.** `set_visible(True)` does not map a widget — GTK does
        # that in the next layout pass — and `adw_animation_play()` on an
        # unmapped widget has no frame clock to drive it, so it skips
        # straight to the end. Called on the line after `set_visible(True)`,
        # which is the only sensible place to call it from, every one of
        # these fades would silently not happen and the opacity would land
        # at 1 before the first frame. Waiting for the map that
        # `set_visible(True)` has already queued is what makes it real.
        if self._map_handler is None:
            self._map_handler = self._widget.connect("map", self._on_mapped)

    def _on_mapped(self, _widget: Gtk.Widget) -> None:
        self._disconnect_map()
        self._animation.play()

    def _disconnect_map(self) -> None:
        if self._map_handler is not None:
            self._widget.disconnect(self._map_handler)
            self._map_handler = None

    def finish(self) -> None:
        """Land on fully opaque now. A surface closed mid-fade would
        otherwise keep the opacity it had when it went, and the next thing
        to show it without going through `play()` would be a ghost."""
        self._disconnect_map()
        self._animation.skip()
        self._widget.set_opacity(1.0)


class Fadable(Protocol):
    """What `HomeView` needs of a surface to hand it the motion setting."""

    def set_fade_enabled(self, enabled: bool) -> None: ...


class FadesIn:
    """Mixin giving a full-screen surface its opening fade.

    A mixin rather than a base class because these surfaces are already
    `Gtk.Box`, `Gtk.Overlay` and `Gtk.Widget` subclasses and have nothing
    else in common. Each one calls `_begin_fade()` on the line after its
    own `set_visible(True)`.
    """

    _fade: FadeIn | None = None

    def _init_fade(self, base_ms: int = SCREEN_FADE_MS) -> None:
        assert isinstance(self, Gtk.Widget)
        self._fade = FadeIn(self, base_ms)

    def set_fade_enabled(self, enabled: bool) -> None:
        if self._fade is not None:
            self._fade.set_enabled(enabled)

    def _begin_fade(self) -> None:
        if self._fade is not None:
            self._fade.play()
