# SPDX-License-Identifier: GPL-3.0-or-later
"""Global animation speed and shared motion parameters."""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
from gi.repository import (  # noqa: E402
    Adw,  # noqa: E402
)

# Tighter than the brief's literal 0.82/320 — that combination read as
# loose and bouncy on a real screen. A higher damping
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
