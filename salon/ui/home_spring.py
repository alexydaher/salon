# SPDX-License-Identifier: GPL-3.0-or-later
# ruff: noqa: F403, F405
"""Home row-axis animation."""

from salon.ui.home_shared import *


class _AxisSpring:
    """Animates one translate offset along one axis, reapplying it as a
    Gsk.Transform on `child` within `viewport` every tick.

    Shared by the vertical row anchor and each row's horizontal tile scroll,
    so both move with the same physics. Gsk.Transform is immutable with
    chaining semantics in PyGObject (§11) — every value has to be reassigned,
    never mutated in place.
    """

    def __init__(
        self,
        viewport: Gtk.Fixed,
        child: Gtk.Widget,
        *,
        vertical: bool,
        on_value: Callable[[float], None] | None = None,
    ) -> None:
        self._viewport = viewport
        self._child = child
        self._vertical = vertical
        self._value = 0.0
        self._resting = 0.0
        self._animations_enabled = True
        # Called on every frame of the animation, not just when it settles:
        # the band's edge fades are a function of how far the content has
        # actually moved, and reading the target instead would snap them to
        # full strength while the rows were still travelling.
        self._on_value = on_value

        params = Adw.SpringParams.new(SPRING_DAMPING_RATIO, SPRING_MASS, SPRING_STIFFNESS)
        target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._animation = Adw.SpringAnimation.new(viewport, 0.0, 0.0, params, target)

        bump_target = Adw.CallbackAnimationTarget.new(self._on_tick)
        self._bump_animation = Adw.TimedAnimation.new(viewport, 0.0, 0.0, _BUMP_MS, bump_target)
        self._bump_animation.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self._bump_animation.connect("done", self._on_bump_done)

    def set_animations_enabled(self, enabled: bool) -> None:
        self._animations_enabled = enabled

    @property
    def value(self) -> float:
        return self._value

    def _on_tick(self, value: float) -> None:
        self._value = value
        dx, dy = (0.0, value) if self._vertical else (value, 0.0)
        self._viewport.set_child_transform(self._child, _translate(dx, dy))
        if self._on_value is not None:
            self._on_value(value)

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
        """§6.2's rubber-band: a short overshoot away from the boundary that
        springs back, so hitting the end of a row is felt rather than
        silently ignored."""
        if not self._animations_enabled:
            return
        self._animation.pause()
        self._bump_animation.set_value_from(self._resting)
        self._bump_animation.set_value_to(self._resting + distance)
        self._bump_animation.play()

    def _on_bump_done(self, _animation: Adw.Animation) -> None:
        target = self._resting
        self._animation.set_value_from(self._value)
        self._animation.set_value_to(target)
        self._animation.play()


__all__ = [name for name in globals() if not name.startswith("__")]
