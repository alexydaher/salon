# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from salon.input.actions import Action, Repeater, RepeaterTiming


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_no_repeat_before_initial_delay() -> None:
    clock = FakeClock()
    repeater = Repeater(clock)
    repeater.press(Action.RIGHT)
    clock.advance(0.399)
    assert repeater.poll() is None


def test_fires_at_initial_delay() -> None:
    clock = FakeClock()
    repeater = Repeater(clock)
    repeater.press(Action.RIGHT)
    clock.advance(0.4)
    assert repeater.poll() is Action.RIGHT


def test_repeats_at_interval_until_fast_after_threshold() -> None:
    clock = FakeClock()
    repeater = Repeater(clock)
    repeater.press(Action.DOWN)
    clock.advance(0.4)
    assert repeater.poll() is Action.DOWN  # repeat 1
    clock.advance(0.12)
    assert repeater.poll() is Action.DOWN  # repeat 2
    clock.advance(0.11)
    assert repeater.poll() is None  # not yet


def test_ramps_to_fast_interval_after_six_repeats() -> None:
    clock = FakeClock()
    repeater = Repeater(clock)
    repeater.press(Action.DOWN)
    clock.advance(0.4)
    for _ in range(6):
        assert repeater.poll() is Action.DOWN
        clock.advance(0.12)
    # 7th repeat onward should use the fast interval.
    assert repeater.poll() is Action.DOWN
    clock.advance(0.04)
    assert repeater.poll() is None
    clock.advance(0.03)
    assert repeater.poll() is Action.DOWN


def test_release_stops_repeating() -> None:
    clock = FakeClock()
    repeater = Repeater(clock)
    repeater.press(Action.LEFT)
    repeater.release()
    clock.advance(10.0)
    assert repeater.poll() is None


def test_press_resets_repeat_count() -> None:
    clock = FakeClock()
    timing = RepeaterTiming(initial_delay=0.0, interval=0.1, fast_interval=0.05, fast_after=1)
    repeater = Repeater(clock, timing)
    repeater.press(Action.UP)
    assert repeater.poll() is Action.UP
    clock.advance(0.1)
    assert repeater.poll() is Action.UP  # now past fast_after, using fast_interval
    repeater.press(Action.UP)
    assert repeater.poll() is Action.UP  # initial_delay elapsed immediately again
    clock.advance(0.05)
    assert repeater.poll() is None  # back to the slow interval, not yet due
    clock.advance(0.06)
    assert repeater.poll() is Action.UP
