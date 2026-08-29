# SPDX-License-Identifier: GPL-3.0-or-later
"""The three things a settings value can be, drawn rather than spelled.

A television settings screen that prints `Off`, `#D9584B` and `4.5%` has
told you the truth and shown you nothing. Each of these replaces one of
those strings with the thing it describes:

* `Switch` — a pill, because "On"/"Off" as a word in the accent colour read
  as *on* either way at three metres (the value column is `@accent`, and a
  glowing "Off" is the worst possible answer).
* `Swatch` — the colour, on the one kind of setting whose entire content is
  a colour and which used to be a name or a hex string.
* `Meter` — where a range sits in its span, so "Safe area 4.5%" is a
  position rather than a number to be compared against a remembered one.

All three take their colour from CSS `color`, which GTK resolves per widget
and per state — so a theme change repaints them with everything else and
none of the palette lives in Python. `Swatch` is the exception and has to
be told its colour, because that colour *is* the value.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")

from gi.repository import Gdk, Graphene, Gsk, Gtk  # noqa: E402

_TRACK_ALPHA = 0.22
_RING_ALPHA = 0.35


def _tinted(color: Gdk.RGBA, alpha: float) -> Gdk.RGBA:
    faded = Gdk.RGBA()
    faded.red, faded.green, faded.blue = color.red, color.green, color.blue
    faded.alpha = color.alpha * alpha
    return faded


def _rect(x: float, y: float, w: float, h: float) -> Graphene.Rect:
    """Never `Graphene.Rect().init(...)`.

    The `init*` methods fill the struct in place and *also* return a
    pointer to it, and PyGObject wraps that return value without owning the
    memory — so using it gives a struct full of whatever was on the stack.
    A `Gsk.RoundedRect` built that way had a width of 1.18e12, which as a
    clip discards everything drawn inside it: the switch, the swatch and
    the meter all rendered as nothing at all, on a screen where every other
    widget was fine. `ui/tile_geometry.py` has always done it this way;
    this file did not, and that is the whole of the bug.
    """
    rect = Graphene.Rect()
    rect.init(x, y, w, h)
    return rect


def _rounded_rect(rect: Graphene.Rect, radius: float) -> Gsk.RoundedRect:
    rounded = Gsk.RoundedRect()
    rounded.init_from_rect(rect, radius)
    return rounded


def _rounded(snapshot: Gtk.Snapshot, x: float, y: float, w: float, h: float, r: float) -> None:
    snapshot.push_rounded_clip(_rounded_rect(_rect(x, y, w, h), r))


class Switch(Gtk.Widget):
    """A pill with a knob. Reports state; it is never pressed directly —
    the row owns the press, from OK, RIGHT, a click or the phone."""

    def __init__(self) -> None:
        super().__init__()
        self.add_css_class("salon-switch")
        self.set_can_target(False)
        self._on = False

    def set_on(self, on: bool) -> None:
        if on == self._on:
            return
        self._on = on
        if on:
            self.add_css_class("on")
        else:
            self.remove_css_class("on")
        self.queue_draw()

    def set_metrics(self, width: int, height: int) -> None:
        self.set_size_request(width, height)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width, height = float(self.get_width()), float(self.get_height())
        if width <= 0 or height <= 0:
            return
        color = self.get_color()
        radius = height / 2.0
        _rounded(snapshot, 0, 0, width, height, radius)
        snapshot.append_color(
            color if self._on else _tinted(color, _TRACK_ALPHA),
            _rect(0, 0, width, height),
        )
        snapshot.pop()

        inset = height * 0.16
        knob = height - inset * 2
        x = width - inset - knob if self._on else inset
        _rounded(snapshot, x, inset, knob, knob, knob / 2.0)
        # The knob is the surface behind the row, not white: on the "on"
        # side it is a hole punched in the accent, which is what makes the
        # two states different in shape as well as in colour.
        snapshot.append_color(
            _tinted(color, 1.0) if not self._on else _knob_on(),
            _rect(x, inset, knob, knob),
        )
        snapshot.pop()


def _knob_on() -> Gdk.RGBA:
    """Near-black, so the knob reads as cut out of the accent fill.

    Not taken from CSS: it has to contrast with `color`, and a token that
    is "whatever the accent is not" is a rule, not a colour.
    """
    color = Gdk.RGBA()
    color.parse("#101014")
    return color


class Swatch(Gtk.Widget):
    """A rounded chip of one colour, with a hairline so a dark accent on a
    dark row still has an edge."""

    def __init__(self) -> None:
        super().__init__()
        self.add_css_class("salon-swatch")
        self.set_can_target(False)
        self._color: Gdk.RGBA | None = None

    def set_color(self, spec: str) -> bool:
        """Show `spec`, or nothing at all if it isn't a colour. Returns
        whether it took, so the caller can fall back to printing the text
        — an unparseable accent is a typo worth seeing, not a blank chip."""
        color = Gdk.RGBA()
        parsed = bool(spec) and color.parse(spec)
        self._color = color if parsed else None
        self.set_visible(parsed)
        self.queue_draw()
        return parsed

    def set_metrics(self, size: int) -> None:
        self.set_size_request(size, size)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width, height = float(self.get_width()), float(self.get_height())
        if self._color is None or width <= 0 or height <= 0:
            return
        radius = min(width, height) * 0.3
        _rounded(snapshot, 0, 0, width, height, radius)
        snapshot.append_color(self._color, _rect(0, 0, width, height))
        snapshot.pop()
        edge = max(1.0, height * 0.06)
        snapshot.append_border(
            _rounded_rect(_rect(0, 0, width, height), radius),
            [edge] * 4,
            [_tinted(self.get_color(), _RING_ALPHA)] * 4,
        )


class Meter(Gtk.Widget):
    """A track with a filled prefix: where this value sits in its range."""

    def __init__(self) -> None:
        super().__init__()
        self.add_css_class("salon-meter")
        self.set_can_target(False)
        self._fraction = 0.0

    def set_fraction(self, fraction: float) -> None:
        clamped = min(1.0, max(0.0, fraction))
        if abs(clamped - self._fraction) < 1e-6:
            return
        self._fraction = clamped
        self.queue_draw()

    def set_metrics(self, width: int, height: int) -> None:
        self.set_size_request(width, height)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width, height = float(self.get_width()), float(self.get_height())
        if width <= 0 or height <= 0:
            return
        color = self.get_color()
        radius = height / 2.0
        _rounded(snapshot, 0, 0, width, height, radius)
        snapshot.append_color(_tinted(color, _TRACK_ALPHA), _rect(0, 0, width, height))
        snapshot.pop()
        # A floor of one track-height, so the minimum of a range is a dot
        # rather than nothing — "empty" and "at the bottom" are different
        # answers and the second one is the common case.
        filled = max(height, width * self._fraction)
        _rounded(snapshot, 0, 0, filled, height, radius)
        snapshot.append_color(color, _rect(0, 0, filled, height))
        snapshot.pop()
