# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from salon.input.actions import Action, Repeater, RepeaterTiming, stick_deflection


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


# --- analogue sticks -------------------------------------------------------
#
# The numbers here are measurements, not choices: a DualSense at rest reports
# +0.11..+0.15 on both Y axes continuously. Anything that treats that as
# motion drifts the pointer down the screen with the controller on the table.


def test_a_stick_at_rest_is_not_motion() -> None:
    for resting in (0.0, 0.079, 0.111, 0.134, 0.142, 0.150, 0.25):
        assert stick_deflection(resting, 0.25) == 0.0
        assert stick_deflection(-resting, 0.25) == 0.0


def test_deflection_starts_from_zero_at_the_dead_zone_edge() -> None:
    """A threshold is not a floor. Passing the raw value straight through
    once it clears the dead zone means the slowest speed available is the
    dead zone itself, and the cursor jumps rather than creeps."""
    just_past = stick_deflection(0.2501, 0.25)
    assert 0.0 < just_past < 0.01


def test_full_deflection_is_full_speed() -> None:
    assert stick_deflection(1.0, 0.25) == pytest.approx(1.0)
    assert stick_deflection(-1.0, 0.25) == pytest.approx(-1.0)
    # Sticks can read slightly past their nominal range on the diagonals.
    assert stick_deflection(1.4, 0.25) == pytest.approx(1.0)


def test_the_scale_is_linear_between_the_two() -> None:
    half = stick_deflection(0.25 + 0.75 / 2, 0.25)
    assert half == pytest.approx(0.5)


def test_sign_is_preserved() -> None:
    assert stick_deflection(-0.625, 0.25) == pytest.approx(-0.5)


def test_a_dead_zone_of_one_silences_the_stick_without_dividing_by_zero() -> None:
    """Degenerate, but a settings key could produce it one day, and a
    ZeroDivisionError in the input path takes the whole interface out."""
    assert stick_deflection(1.0, 1.0) == 0.0
    assert stick_deflection(-1.0, 1.0) == 0.0
    # Sticks do read past their nominal range; that must not divide either.
    assert stick_deflection(1.4, 1.0) == 1.0
