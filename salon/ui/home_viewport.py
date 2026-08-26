# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Home viewport clipping and fades."""

from salon.ui.home_shared import (
    Gdk,
    Graphene,
    Gsk,
    Gtk,
    _point,
)


def _edge_mask(
    snapshot: Gtk.Snapshot, width: float, height: float, near: float, far: float, *, vertical: bool
) -> None:
    """Push an alpha mask that ramps content in over `near` at the start of
    one axis and out over `far` at its end.

    Shared by the band (vertical) and by every row (horizontal), because a
    row sliced off by a hard clip edge reads as a rendering fault whichever
    edge it is — and until this was factored out, only one of the two axes
    had the treatment: the last tile in a row was guillotined mid-word at
    the screen edge, at whatever position a television's overscan happened
    to put it.

    The caller pops twice: once for the mask, once for the content.
    """
    bounds = Graphene.Rect()
    bounds.init(0.0, 0.0, width, height)
    span = height if vertical else width

    snapshot.push_mask(Gsk.MaskMode.ALPHA)
    opaque = Gdk.RGBA()
    opaque.red = opaque.green = opaque.blue = opaque.alpha = 1.0
    clear = Gdk.RGBA()
    clear.red = clear.green = clear.blue = clear.alpha = 0.0
    stops = []
    for offset, color in (
        (0.0, clear),
        (near / span, opaque),
        (1.0 - far / span, opaque),
        (1.0, clear),
    ):
        stop = Gsk.ColorStop()
        stop.offset = max(0.0, min(1.0, offset))
        stop.color = color
        stops.append(stop)
    end = _point(0.0, span) if vertical else _point(span, 0.0)
    snapshot.append_linear_gradient(bounds, _point(0.0, 0.0), end, stops)
    snapshot.pop()


class _RowViewport(Gtk.Fixed):
    """One row's horizontal clip, faded at whichever end has tiles past it.

    The vertical twin of this is `_LayoutViewport` below and the reasoning
    is identical, but the horizontal case has two extra constraints.

    The first is that the focused tile is left-anchored *at the safe-area
    margin*, and the last tile of a row comes to rest flush against the
    right one. So the ramp can never be wider than that margin, or the tile
    the user is looking at is the one being faded. `_RowWidgets` passes the
    smaller of the two.

    The second is that **this widget is wider than the window.** A Gtk.Fixed
    measures to fit its children and its parent here is another Gtk.Fixed,
    which hands out natural sizes — so a row of four tiles is allocated 1468
    px inside a 1280 px window whatever size request it was given, and the
    real clip is the window edge rather than this widget's. Taking
    `get_width()` as the right-hand edge therefore drew the ramp 188 px past
    the screen, where it faded nothing at all: the fade looked implemented,
    passed every reading of the code, and did not exist on the display.
    So the visible span is passed in from the layout pass, which knows the
    window's width, rather than measured here. (This is the horizontal face
    of the Gtk.Fixed sizing trap in CLAUDE.md; it has now been hit on both
    axes.)
    """

    def __init__(self) -> None:
        super().__init__()
        self._left_fade = 0.0
        self._right_fade = 0.0
        self._span = 0.0

    def set_fades(self, left: float, right: float, span: float) -> None:
        if (left, right, span) == (self._left_fade, self._right_fade, self._span):
            return
        self._left_fade = left
        self._right_fade = right
        self._span = span
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        span = self._span if self._span > 0 else float(self.get_width())
        height = float(self.get_height())
        if span <= 0 or height <= 0 or (self._left_fade <= 0 and self._right_fade <= 0):
            Gtk.Fixed.do_snapshot(self, snapshot)
            return
        _edge_mask(snapshot, span, height, self._left_fade, self._right_fade, vertical=False)
        Gtk.Fixed.do_snapshot(self, snapshot)
        snapshot.pop()


class _LayoutViewport(Gtk.Fixed):
    """A Gtk.Fixed that reports its own resizes and fades out at the top and
    bottom edges.

    The resize part exists because every layout constant here is derived
    from the window's real size and Gtk.Widget has no resize signal, so the
    one place that knows the size changed is size_allocate.

    The fade exists because the rows are taller than the screen whenever
    there are more than about three of them, and a row sliced off by a hard
    clip edge reads as a rendering fault. Masking the *rows* rather than
    painting a scrim over them keeps the backdrop's ambient glow intact
    underneath. Each end is faded by however much is actually overhanging
    it, so an end with nothing past it is not faded at all — a constant ramp
    at the top dimmed the first row's heading permanently.

    It used to be doing a second job as well, and no longer is. The fades
    were the width of the two bars — the status strip and the detail strip —
    because this viewport spanned the whole window and rows really did pass
    behind the clock; dimming them was what kept the clock readable. The
    viewport is now inset to the gap between the bars instead
    (`HomeView._apply_viewport_insets`), so nothing overlaps them at all and
    what is left here is a short softening of the band's own edges.
    """

    def __init__(self) -> None:
        super().__init__()
        self._top_fade = 0.0
        self._bottom_fade = 0.0

    def set_fades(self, top: float, bottom: float) -> None:
        self._top_fade = top
        self._bottom_fade = bottom
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0 or (self._top_fade <= 0 and self._bottom_fade <= 0):
            Gtk.Fixed.do_snapshot(self, snapshot)
            return

        _edge_mask(snapshot, width, height, self._top_fade, self._bottom_fade, vertical=True)
        Gtk.Fixed.do_snapshot(self, snapshot)
        snapshot.pop()


__all__ = [name for name in globals() if not name.startswith("__")]
