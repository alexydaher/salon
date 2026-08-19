# SPDX-License-Identifier: GPL-3.0-or-later
"""The shared input action vocabulary. Pure — no gi.

All input sources (keyboard, gamepad, CEC) normalize to this enum before
anything else sees them; adding a new input source is one new file that
emits Action values, and nothing downstream has to change.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    OK = "ok"
    BACK = "back"
    MENU = "menu"
    # The per-item context menu: "what else can I do with the thing under
    # the cursor". Separate from MENU, which is the global system menu and
    # has to stay the one button that always means the same thing.
    OPTIONS = "options"
    SEARCH = "search"
    PLAY_PAUSE = "play_pause"
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    MUTE = "mute"
    POWER = "power"


@dataclass(frozen=True, slots=True)
class RepeaterTiming:
    initial_delay: float = 0.4
    interval: float = 0.12
    fast_interval: float = 0.06
    fast_after: int = 6


_DEFAULT_TIMING = RepeaterTiming()


class Repeater:
    """Key-repeat acceleration for a held direction, per §6.2: 400ms initial
    delay, then 120ms interval, ramping to 60ms after six repeats.

    Driven by an injected clock (seconds, monotonic) so it's testable
    without real time — the caller (an input source) calls press() on
    key-down, poll() on every tick while held, and release() on key-up.
    """

    def __init__(
        self, clock: Callable[[], float], timing: RepeaterTiming = _DEFAULT_TIMING
    ) -> None:
        self._clock = clock
        self._timing = timing
        self._action: Action | None = None
        self._next_fire: float = 0.0
        self._repeat_count: int = 0

    def press(self, action: Action) -> None:
        self._action = action
        self._next_fire = self._clock() + self._timing.initial_delay
        self._repeat_count = 0

    def release(self) -> None:
        self._action = None

    def poll(self) -> Action | None:
        """Returns the held action if its repeat interval has elapsed since
        the last fire, else None. Call this frequently (e.g. every frame)
        while a direction is held."""
        if self._action is None:
            return None
        now = self._clock()
        if now < self._next_fire:
            return None
        interval = (
            self._timing.fast_interval
            if self._repeat_count >= self._timing.fast_after
            else self._timing.interval
        )
        self._next_fire = now + interval
        self._repeat_count += 1
        return self._action


def stick_deflection(value: float, dead_zone: float) -> float:
    """An analogue stick reading, with its dead zone taken out properly.

    Two things a naive `abs(value) < dead_zone` test gets wrong, both
    measured on a real DualSense rather than reasoned about:

    * **A stick at rest is not at zero.** Hands off the controller, that pad
      reports Y deflections of +0.11 to +0.15 on both sticks, continuously,
      at around sixty events a second. Anything treating 0.15 as "moving"
      has a pointer that slides down the screen on its own.
    * **A threshold is not a floor.** Passing the raw value through once it
      clears the dead zone means the slowest motion available is whatever
      the dead zone was — the cursor jumps from stationary to a quarter
      speed. Rescaling the remaining range back to 0..1 gives a stick that
      starts from nothing and reaches full speed at full deflection.

    Returns a value in -1..1, signed like the input.
    """
    magnitude = abs(value)
    if magnitude <= dead_zone:
        return 0.0
    span = 1.0 - dead_zone
    if span <= 0.0:
        return math.copysign(1.0, value)
    return math.copysign(min(1.0, (magnitude - dead_zone) / span), value)
