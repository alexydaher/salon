# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK allocation reporting and GSK geometry constructors."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Graphene, Gsk, Gtk  # noqa: E402


class SizeReporter(Gtk.Widget):
    """A single-child wrapper that reports its allocation.

    Learning a widget's own size sounds like a `do_size_allocate` override,
    and on a `Gtk.Fixed` (or a `Gtk.Box`) that override silently never
    runs: GTK4 dispatches allocation to the layout manager *instead of* the
    widget class vfunc whenever one is set, and those containers each
    install one. Swapping the layout manager isn't an option either —
    `GtkFixed` caches the one it made in `init` and `put`/`move`/
    `set_child_transform` all go through that cached pointer.

    A plain `Gtk.Widget` has no layout manager, so its vfunc is the thing
    GTK actually calls. This wraps the container in one of those and hands
    the real size back.

    `propagate_minimum=False` is what makes one of these a **scroll
    viewport** rather than a plain wrapper. A `Gtk.Fixed` measures to fit
    its children, so a clipping viewport around content taller than the
    screen asks to *be* that tall — and gets it, because an overlay child
    is happily allocated more than the window. The clip then happens at the
    window edge instead of at the viewport's, the reported height is the
    content's height, and every "is the focused row off-screen?" test
    silently answers no: the list stops scrolling and everything past the
    first screenful is unreachable. Reporting a zero minimum hands the
    decision back to the parent, which is the only thing that knows how
    much room there actually is.
    """

    def __init__(
        self,
        child: Gtk.Widget,
        on_resize: Callable[[int, int], None],
        *,
        propagate_minimum: bool = True,
    ) -> None:
        super().__init__()
        self._child = child
        self._on_resize = on_resize
        self._propagate_minimum = propagate_minimum
        self._last = (-1, -1)
        child.set_parent(self)

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        if not self._propagate_minimum:
            return (0, 0, -1, -1)
        minimum, natural, min_base, nat_base = self._child.measure(orientation, for_size)
        return (minimum, natural, min_base, nat_base)

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        self._child.allocate(width, height, baseline, None)
        if (width, height) != self._last:
            self._last = (width, height)
            self._on_resize(width, height)

    def do_dispose(self) -> None:
        # A Gtk.Widget subclass owns its children explicitly; without this
        # GTK warns that the child is still parented at finalize.
        if self._child is not None:
            self._child.unparent()
            self._child = None  # type: ignore[assignment]
        Gtk.Widget.do_dispose(self)


def point(x: float, y: float) -> Graphene.Point:
    result = Graphene.Point()
    result.init(x, y)
    return result


def rect(x: float, y: float, width: float, height: float) -> Graphene.Rect:
    result = Graphene.Rect()
    result.init(x, y, width, height)
    return result


def translate(dx: float, dy: float) -> Gsk.Transform:
    return Gsk.Transform.new().translate(point(dx, dy))
