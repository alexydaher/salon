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

        bounds = Graphene.Rect()
        bounds.init(0.0, 0.0, width, height)

        snapshot.push_mask(Gsk.MaskMode.ALPHA)
        opaque = Gdk.RGBA()
        opaque.red = opaque.green = opaque.blue = opaque.alpha = 1.0
        clear = Gdk.RGBA()
        clear.red = clear.green = clear.blue = clear.alpha = 0.0
        stops = []
        for offset, color in (
            (0.0, clear),
            (self._top_fade / height, opaque),
            (1.0 - self._bottom_fade / height, opaque),
            (1.0, clear),
        ):
            stop = Gsk.ColorStop()
            stop.offset = max(0.0, min(1.0, offset))
            stop.color = color
            stops.append(stop)
        snapshot.append_linear_gradient(bounds, _point(0.0, 0.0), _point(0.0, height), stops)
        snapshot.pop()

        Gtk.Fixed.do_snapshot(self, snapshot)
        snapshot.pop()


__all__ = [name for name in globals() if not name.startswith("__")]
