# SPDX-License-Identifier: GPL-3.0-or-later
"""Spring-driven translation along one scrolling axis."""
from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk  # noqa: E402

from salon.ui.motion_geometry import translate  # noqa: E402
from salon.ui.motion_settings import BUMP_MS, duration_ms, spring_params  # noqa: E402


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
