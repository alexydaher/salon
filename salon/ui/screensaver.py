# SPDX-License-Identifier: GPL-3.0-or-later
"""The idle screen: what a television shows when nobody is using it.

Salon sits at full brightness indefinitely. On a desk that is fine, because
the desktop's own screensaver takes over; in Salon's own session it is
configured by the session administrator, because a launcher that
demands a password when someone picks up the remote is a dead end in a
living room. The consequence is a static, bright, high-contrast image left
on a panel for hours — which on the OLED televisions this is aimed at is
not a taste question. The tile ring and the status bar never move.

So: after a few minutes with no input, everything fades down to a clock
that drifts slowly around the screen, and any button at all brings it back.
The drift is the point — a clock parked in a corner for six hours is the
same problem in smaller letters. It moves continuously rather than jumping,
because a jump would read as a fault and because continuous motion at this
speed is what stops a static edge forming anywhere.

Deliberately not a lock: there is no password, nothing is hidden, and the
first press of any key both dismisses this and is *swallowed* rather than
acted on. Waking a screen must never launch something.

`screensaver-minutes` sets the delay; 0 turns it off for anyone who would
rather it did not exist.
"""

from __future__ import annotations

import math
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")

from gi.repository import Adw, Gdk, GLib, Graphene, Gtk, Pango  # noqa: E402

from salon.core import tokens  # noqa: E402
from salon.ui import motion, theme  # noqa: E402
from salon.ui.scale import Scale  # noqa: E402
from salon.ui.tile import DISPLAY_FAMILY, font_description  # noqa: E402

_FADE_MS = 1200

# How far around the screen the clock wanders, as a fraction of the space
# left over once the text is placed, and how long one full circuit takes.
# Slow enough not to be motion anyone watches, fast enough that no pixel
# holds the same bright text for more than a couple of minutes.
_DRIFT_PERIOD_SECONDS = 137.0
_DRIFT_TICK_MS = 500

# Well below the interface it replaces. Bright enough to read across a
# room, dim enough to be no worse for the panel than a dark image.
_TEXT_ALPHA = 0.55
_DATE_ALPHA = 0.30


def _parse(value: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.parse(value)
    return color


def _with_alpha(color: Gdk.RGBA, alpha: float) -> Gdk.RGBA:
    faded = Gdk.RGBA()
    faded.red, faded.green, faded.blue = color.red, color.green, color.blue
    faded.alpha = alpha
    return faded


class ScreenSaver(Gtk.Widget):
    """A drifting clock over an opaque field. Drawn rather than built from
    labels because the position changes every half second and moving a
    widget that often means a layout pass that often."""

    def __init__(self, scale: Scale) -> None:
        super().__init__()
        self.set_visible(False)
        self.set_can_target(False)
        self.set_hexpand(True)
        self.set_vexpand(True)
        # Nothing here is information a screen reader wants: it is the
        # absence of the interface, and the interface underneath is still
        # the thing being described.
        self.set_accessible_role(Gtk.AccessibleRole.PRESENTATION)

        self._scale = scale
        self._opacity = 0.0
        self._phase = 0.0
        self._tick_id: int | None = None

        target = Adw.CallbackAnimationTarget.new(self._on_fade)
        self._fade = Adw.TimedAnimation.new(self, 0.0, 1.0, _FADE_MS, target)
        self._fade.set_easing(Adw.Easing.EASE_OUT_CUBIC)

    def set_scale(self, scale: Scale) -> None:
        self._scale = scale
        self.queue_draw()

    # --- lifecycle -------------------------------------------------------

    @property
    def showing(self) -> bool:
        return self.get_visible()

    def show(self) -> None:
        if self.get_visible():
            return
        self.set_visible(True)
        self._opacity = 0.0
        self._fade.set_value_from(0.0)
        self._fade.set_value_to(1.0)
        self._fade.set_duration(motion.duration_ms(_FADE_MS))
        self._fade.reset()
        self._fade.play()
        if self._tick_id is None:
            self._tick_id = GLib.timeout_add(_DRIFT_TICK_MS, self._on_tick)

    def hide(self) -> None:
        """Straight off, not faded.

        Someone has just pressed a button and is waiting to see the screen
        they asked for; a second of dissolve between the press and the
        interface is a second of wondering whether the press registered.
        """
        if not self.get_visible():
            return
        self._fade.pause()
        self.set_visible(False)
        self._opacity = 0.0
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None

    def do_unroot(self) -> None:
        if self._tick_id is not None:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
        Gtk.Widget.do_unroot(self)

    def _on_fade(self, value: float) -> None:
        self._opacity = value
        self.queue_draw()

    def _on_tick(self) -> bool:
        self._phase += _DRIFT_TICK_MS / 1000.0 / _DRIFT_PERIOD_SECONDS
        self.queue_draw()
        return bool(GLib.SOURCE_CONTINUE)

    # --- drawing ---------------------------------------------------------

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0 or self._opacity <= 0.0:
            return

        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)
        snapshot.append_color(_with_alpha(theme.color("surface-0"), self._opacity), bounds)

        now = datetime.now()
        clock = self._layout(now.strftime("%H:%M"), tokens.type_token("clock").size_du * 2.4, 700)
        date = self._layout(now.strftime("%A, %-d %B"), tokens.type_token("date").size_du, 400)
        clock_width, clock_height = clock.get_pixel_size()
        date_width, date_height = date.get_pixel_size()
        block_width = max(clock_width, date_width)
        block_height = clock_height + date_height

        # Lissajous rather than a straight bounce: two incommensurable
        # frequencies never retrace the same path, so no pixel accumulates
        # more exposure than any other over an evening.
        margin = self._scale.du(tokens.REFERENCE_VIEWPORT_HEIGHT_PX * 0.08)
        span_x = max(0.0, width - block_width - 2 * margin)
        span_y = max(0.0, height - block_height - 2 * margin)
        angle = self._phase * 2.0 * math.pi
        x = margin + span_x * (0.5 + 0.5 * math.sin(angle))
        y = margin + span_y * (0.5 + 0.5 * math.sin(angle * 1.618 + 1.1))

        point = Graphene.Point()
        point.init(x + (block_width - clock_width) / 2.0, y)
        snapshot.save()
        snapshot.translate(point)
        snapshot.append_layout(
            clock, _with_alpha(theme.color("text-primary"), _TEXT_ALPHA * self._opacity)
        )
        snapshot.restore()

        point = Graphene.Point()
        point.init(x + (block_width - date_width) / 2.0, y + clock_height)
        snapshot.save()
        snapshot.translate(point)
        snapshot.append_layout(
            date, _with_alpha(theme.color("text-primary"), _DATE_ALPHA * self._opacity)
        )
        snapshot.restore()

    def _layout(self, text: str, size_du: float, weight: int) -> Pango.Layout:
        layout = self.create_pango_layout(text)
        layout.set_font_description(
            font_description(DISPLAY_FAMILY, self._scale.du(size_du), weight)
        )
        return layout
