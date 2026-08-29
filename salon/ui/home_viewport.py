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


def _white(alpha: float) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red = color.green = color.blue = 1.0
    color.alpha = alpha
    return color


def _rect(x: float, y: float, width: float, height: float) -> Graphene.Rect:
    bounds = Graphene.Rect()
    bounds.init(x, y, width, height)
    return bounds


def _snapshot_faded(
    container: Gtk.Fixed,
    snapshot: Gtk.Snapshot,
    width: float,
    height: float,
    near: float,
    far: float,
    *,
    vertical: bool,
) -> None:
    """Draw `container`'s children, ramping them in over `near` at the start
    of one axis and out over `far` at its end.

    Shared by the band (vertical) and by every row (horizontal), because a
    row sliced off by a hard clip edge reads as a rendering fault whichever
    edge it is — and until this was factored out, only one of the two axes
    had the treatment: the last tile in a row was guillotined mid-word at
    the screen edge, at whatever position a television's overscan happened
    to put it.

    **The mask is pushed over the ramps alone, not over the whole band**,
    and that is a performance decision rather than a visual one. A
    `Gsk.MaskMode.ALPHA` node makes GSK render both of its children into
    offscreen images the size of the masked area; masking the whole widget
    therefore bought two full-size offscreens per row per frame, nine of
    them together with the band, and on a 5K display that was eleven
    milliseconds of every frame — the home screen scrolled at 36fps with
    them and at a locked 60 without. The picture is identical: the middle
    of the band is opaque under a full-width mask, so drawing it under a
    plain clip instead changes nothing except how much offscreen the GPU
    allocates. The children are snapshotted once per part, which costs
    nothing extra — GTK caches each child's render node and reuses it when
    the child is not itself dirty.
    """
    span = height if vertical else width
    if span <= 0:
        return
    near = max(0.0, min(near, span / 2.0))
    far = max(0.0, min(far, span - near))

    def part(start: float, length: float, ramp: tuple[float, float] | None) -> None:
        if length <= 0:
            return
        clip = _rect(0.0, start, width, length) if vertical else _rect(start, 0.0, length, height)
        snapshot.push_clip(clip)
        if ramp is not None:
            snapshot.push_mask(Gsk.MaskMode.ALPHA)
            stops = []
            for offset, alpha in ((0.0, ramp[0]), (1.0, ramp[1])):
                stop = Gsk.ColorStop()
                stop.offset = offset
                stop.color = _white(alpha)
                stops.append(stop)
            begin = _point(0.0, start) if vertical else _point(start, 0.0)
            end = _point(0.0, start + length) if vertical else _point(start + length, 0.0)
            snapshot.append_linear_gradient(clip, begin, end, stops)
            snapshot.pop()
        Gtk.Fixed.do_snapshot(container, snapshot)
        if ramp is not None:
            snapshot.pop()
        snapshot.pop()

    part(0.0, near, (0.0, 1.0))
    part(near, span - near - far, None)
    part(span - far, far, (1.0, 0.0))


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
    of the same Gtk.Fixed sizing trap the vertical viewports hit: such a
    container is allocated its *natural* size, whatever it was asked for.)
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
        _snapshot_faded(
            self, snapshot, span, height, self._left_fade, self._right_fade, vertical=False
        )


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
        """Short-circuited like the row's twin: this is called from the row
        anchor's animation tick, so an unconditional `queue_draw` here was
        re-snapshotting the whole band on every frame of every scroll for
        values that had usually not moved."""
        if (top, bottom) == (self._top_fade, self._bottom_fade):
            return
        self._top_fade = top
        self._bottom_fade = bottom
        self.queue_draw()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width = float(self.get_width())
        height = float(self.get_height())
        if width <= 0 or height <= 0 or (self._top_fade <= 0 and self._bottom_fade <= 0):
            Gtk.Fixed.do_snapshot(self, snapshot)
            return

        _snapshot_faded(
            self, snapshot, width, height, self._top_fade, self._bottom_fade, vertical=True
        )


__all__ = [name for name in globals() if not name.startswith("__")]
