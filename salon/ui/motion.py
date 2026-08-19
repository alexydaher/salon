# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared spring-driven translation, used by every scrolling surface.

§6.1's home rows and §6.6's search results both need the same thing: a
`Gtk.Fixed` clipping around content bigger than itself, translated by a
`Gsk.Transform` that a spring drives. Springs rather than eased curves so a
direction reversal mid-flight settles physically instead of snapping onto a
new curve — which is what flicking through a long row actually feels like.

Gsk.Transform is immutable with chaining semantics in PyGObject (§11):
every call returns a new transform rather than mutating the receiver, so
values are always reassigned here, never mutated in place.
"""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")

from gi.repository import Adw, Graphene, Gsk, Gtk  # noqa: E402

# Tighter than the brief's literal 0.82/320 — that combination read as
# loose and bouncy on a real screen (see DECISIONS.md). A higher damping
# ratio cuts the overshoot almost entirely and a higher stiffness keeps it
# fast.
SPRING_DAMPING_RATIO = 0.92
SPRING_MASS = 1.0
SPRING_STIFFNESS = 500.0

# §6.2's boundary rubber-band: a short overshoot-and-settle, because
# silence at a boundary reads as a broken remote.
BUMP_MS = 90


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


class AxisSpring:
    """Animates one translate offset along one axis, reapplying it as a
    Gsk.Transform on `child` within `viewport` every tick."""

    def __init__(self, viewport: Gtk.Fixed, child: Gtk.Widget, *, vertical: bool) -> None:
        self._viewport = viewport
        self._child = child
        self._vertical = vertical
        self._value = 0.0
        self._resting = 0.0
        self._animations_enabled = True

        params = Adw.SpringParams.new(SPRING_DAMPING_RATIO, SPRING_MASS, SPRING_STIFFNESS)
        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.SpringAnimation.new(viewport, 0.0, 0.0, params, target)

        bump_target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._bump_animation = Adw.TimedAnimation.new(viewport, 0.0, 0.0, BUMP_MS, bump_target)
        self._bump_animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self._bump_animation.connect("done", self._on_bump_done)

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = enabled

    def _on_tick(self, value: float) -> None:
        self._value = value
        dx, dy = (0.0, value) if self._vertical else (value, 0.0)
        self._viewport.set_child_transform(self._child, translate(dx, dy))

    def animate_to(self, target_value: float) -> None:
        self._resting = target_value
        if target_value == self._value:
            return
        if not self._animations_enabled:
            self.jump_to(target_value)
            return
        self._animation.set_value_from(self._value)
        self._animation.set_value_to(target_value)
        self._animation.play()

    def jump_to(self, value: float) -> None:
        self._resting = value
        self._on_tick(value)

    def bump(self, distance: float) -> None:
        if not self._animations_enabled:
            return
        self._animation.pause()
        self._bump_animation.set_value_from(self._resting)
        self._bump_animation.set_value_to(self._resting + distance)
        self._bump_animation.play()

    def _on_bump_done(self, _animation: Adw.Animation) -> None:
        self._animation.set_value_from(self._value)
        self._animation.set_value_to(self._resting)
        self._animation.play()
