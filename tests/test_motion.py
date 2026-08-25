# SPDX-License-Identifier: GPL-3.0-or-later
"""The one animation-speed dial every moving thing in Salon reads.

`animation-scale` shipped as a Settings row that wrote a GSettings key
nothing ever read: "Animation speed", including its Off position, changed
nothing at all. These tests are what stops that happening again — they hold
the *contract* the widgets rely on, which is the part a screenshot cannot
check.

The physics claim is the one worth pinning. An `Adw.SpringAnimation` has no
duration to scale; it settles when the spring says so, and its period goes
as sqrt(mass/stiffness). So "twice as fast" is four times the stiffness, and
the damping ratio — dimensionless — must not move, or the *shape* of the
motion changes with the speed instead of just its rate.
"""

from __future__ import annotations

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from salon.ui import motion  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_default_speed():
    """The speed is module state, so a test that leaves it changed would
    quietly rewrite every later assertion in the run."""
    original = motion.animation_speed()
    yield
    motion.set_animation_speed(original)


def test_default_speed_leaves_durations_alone() -> None:
    assert motion.animation_speed() == 1.0
    assert motion.duration_ms(motion.SCREEN_FADE_MS) == motion.SCREEN_FADE_MS
    assert motion.enabled()


def test_speed_divides_durations_because_the_row_says_speed() -> None:
    # Settings → Appearance shows this as a percentage labelled "Animation
    # speed". 200% has to mean *faster*, so the number divides.
    motion.set_animation_speed(2.0)
    assert motion.duration_ms(200) == 100
    motion.set_animation_speed(0.5)
    assert motion.duration_ms(200) == 400


def test_zero_is_off_and_never_divides() -> None:
    motion.set_animation_speed(0.0)
    assert not motion.enabled()
    # Callers route "off" through enabled() and skip the play; duration_ms
    # must still answer with something usable rather than raise or return 0.
    assert motion.duration_ms(200) == 200


def test_a_duration_never_rounds_away_to_nothing() -> None:
    motion.set_animation_speed(2.0)
    assert motion.duration_ms(1) >= 1


def test_negative_speed_is_clamped_to_off() -> None:
    motion.set_animation_speed(-1.0)
    assert motion.animation_speed() == 0.0
    assert not motion.enabled()


def test_spring_stiffness_goes_as_the_square_of_the_speed() -> None:
    base = motion.spring_params()
    motion.set_animation_speed(2.0)
    faster = motion.spring_params()
    assert faster.get_stiffness() == pytest.approx(base.get_stiffness() * 4.0)
    # The shape of the motion is the damping ratio, and it must not move —
    # otherwise a viewer changing the speed also changes how bouncy Salon is.
    assert faster.get_damping_ratio() == pytest.approx(base.get_damping_ratio())
    assert faster.get_mass() == pytest.approx(base.get_mass())


def test_off_leaves_the_spring_at_its_designed_stiffness() -> None:
    """Nothing plays at speed 0, so the params are never used — but they
    must stay finite rather than collapse to zero stiffness, which is a
    spring that never arrives."""
    motion.set_animation_speed(0.0)
    assert motion.spring_params().get_stiffness() == pytest.approx(motion.SPRING_STIFFNESS)
