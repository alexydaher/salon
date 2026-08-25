# SPDX-License-Identifier: GPL-3.0-or-later
"""Everything in Salon that moves, and the one speed dial they all read.

Three things live here. `AxisSpring` is the spring-driven translation every
scrolling surface uses. `FadeIn` is the transition a full-screen surface
plays as it opens. And the module-level animation *speed* is what Settings →
Appearance → "Animation speed" actually changes — durations divide by it and
spring stiffness multiplies by its square, so one dial moves the whole
system without any widget knowing where the number came from.

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
from typing import Protocol

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

# How long a full-screen surface takes to arrive. Longer than the 90ms bump
# because it is a change of place rather than a nudge, and short enough that
# a remote still feels answered on the press rather than after it.
SCREEN_FADE_MS = 200

# The way back from a launched application. Longer again: under GNOME Kiosk
# there is nothing behind a closing child but the compositor's black, so
# this is the only transition between an application and Salon, and it is
# doing the work Shell's window animations do in the other session.
RETURN_FADE_MS = 320


# --- animation speed ---------------------------------------------------
#
# Settings → Appearance → "Animation speed" (`animation-scale`). Module
# state rather than a value threaded through every constructor: a dozen
# widgets play animations and none of them has any other reason to know
# about GSettings, and the setting is applied live. `home.HomeView` is the
# one writer, from `_apply_animation_setting`.
#
# It is a *speed*, which is what the row says: 200% is twice as fast, so it
# divides durations rather than multiplying them. 0 is off, and every caller
# routes that through `enabled()` rather than dividing by it.
_animation_speed = 1.0


def set_animation_speed(speed: float) -> None:
    global _animation_speed
    _animation_speed = max(0.0, speed)


def animation_speed() -> float:
    return _animation_speed


def enabled() -> bool:
    return _animation_speed > 0.0


def duration_ms(base_ms: int) -> int:
    """`base_ms` at the user's chosen speed, never zero.

    Zero is not this function's answer to "animations off" — a caller that
    is about to `play()` something wants a real duration, and the off case
    belongs to `enabled()`, which skips the play entirely.
    """
    if _animation_speed <= 0.0:
        return base_ms
    return max(1, round(base_ms / _animation_speed))


def spring_params() -> Adw.SpringParams:
    """The shared spring at the user's chosen speed.

    An `Adw.SpringAnimation` has no duration to scale — it settles when the
    physics say so. Its period goes as sqrt(mass/stiffness), so a factor s
    on the speed is a factor s² on the stiffness. Damping ratio is
    dimensionless and stays put, which is what keeps the *shape* of the
    motion (a barely-there overshoot) identical at every speed.
    """
    stiffness = SPRING_STIFFNESS
    if _animation_speed > 0.0:
        stiffness *= _animation_speed**2
    return Adw.SpringParams.new(SPRING_DAMPING_RATIO, SPRING_MASS, stiffness)


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

        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.SpringAnimation.new(viewport, 0.0, 0.0, spring_params(), target)

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
        # Re-read rather than cache: the speed is a live setting, and this
        # is the one place a scroll is about to start.
        self._animation.set_spring_params(spring_params())
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
        self._bump_animation.set_duration(duration_ms(BUMP_MS))
        self._bump_animation.set_value_from(self._resting)
        self._bump_animation.set_value_to(self._resting + distance)
        self._bump_animation.play()

    def _on_bump_done(self, _animation: Adw.Animation) -> None:
        self._animation.set_value_from(self._value)
        self._animation.set_value_to(self._resting)
        self._animation.play()


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
    frame and only its paint is late. See DECISIONS.md 2026-08-23.

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
