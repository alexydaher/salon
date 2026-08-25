# SPDX-License-Identifier: GPL-3.0-or-later
"""Input-neutral actions understood by Salon's domain and application layers."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class Action(StrEnum):
    """A user intent after keyboard, controller, or CEC normalization."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    OK = "ok"
    BACK = "back"
    MENU = "menu"
    OPTIONS = "options"
    SEARCH = "search"
    PREV_GROUP = "prev_group"
    NEXT_GROUP = "next_group"
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
    """Return an accelerating stream of repeated held actions."""

    def __init__(
        self,
        clock: Callable[[], float],
        timing: RepeaterTiming = _DEFAULT_TIMING,
    ) -> None:
        self._clock = clock
        self._timing = timing
        self._action: Action | None = None
        self._next_fire = 0.0
        self._repeat_count = 0

    def press(self, action: Action) -> None:
        self._action = action
        self._next_fire = self._clock() + self._timing.initial_delay
        self._repeat_count = 0

    def release(self) -> None:
        self._action = None

    def poll(self) -> Action | None:
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
    """Remove and rescale an analogue stick dead zone."""
    magnitude = abs(value)
    if magnitude <= dead_zone:
        return 0.0
    span = 1.0 - dead_zone
    if span <= 0.0:
        return math.copysign(1.0, value)
    return math.copysign(min(1.0, (magnitude - dead_zone) / span), value)
