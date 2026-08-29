# SPDX-License-Identifier: GPL-3.0-or-later
"""Fading a clipped container's contents at the edge it clips.

Lives on its own rather than in `home_viewport`, where it grew up, because
the settings lists want the same treatment and reaching into the home
screen for it would drag that whole module graph — config, services, the
catalogue — into `salon.ui.settings.widgets`, which every panel imports.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, Graphene, Gsk, Gtk  # noqa: E402


def _point(x: float, y: float) -> Graphene.Point:
    point = Graphene.Point()
    point.init(x, y)
    return point


def _white(alpha: float) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red = color.green = color.blue = 1.0
    color.alpha = alpha
    return color


def _rect(x: float, y: float, width: float, height: float) -> Graphene.Rect:
    bounds = Graphene.Rect()
    bounds.init(x, y, width, height)
    return bounds


def snapshot_faded(
    container: Gtk.Fixed,
    snapshot: Gtk.Snapshot,
    width: float,
    height: float,
    near: float,
    far: float,
    *,
    vertical: bool,
    draw: Callable[[], None] | None = None,
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
    # `draw` is how a container with children that must *not* fade uses
    # this: the settings lists keep their "▲ More" pills unfaded by drawing
    # only the row box under the mask, then the pills over it. Default is
    # every child, which is what both home viewports want.
    if draw is None:

        def draw() -> None:
            Gtk.Fixed.do_snapshot(container, snapshot)

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
        draw()
        if ramp is not None:
            snapshot.pop()
        snapshot.pop()

    part(0.0, near, (0.0, 1.0))
    part(near, span - near - far, None)
    part(span - far, far, (1.0, 0.0))
