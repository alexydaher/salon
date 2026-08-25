# SPDX-License-Identifier: GPL-3.0-or-later
"""Compatibility facade for shared motion primitives."""

from salon.ui.axis_spring import AxisSpring
from salon.ui.fade import Fadable, FadeIn, FadesIn
from salon.ui.motion_geometry import SizeReporter, point, rect, translate
from salon.ui.motion_settings import (
    BUMP_MS,
    RETURN_FADE_MS,
    SCREEN_FADE_MS,
    SPRING_DAMPING_RATIO,
    SPRING_MASS,
    SPRING_STIFFNESS,
    animation_speed,
    duration_ms,
    enabled,
    set_animation_speed,
    spring_params,
)

__all__ = [
    "BUMP_MS",
    "RETURN_FADE_MS",
    "SCREEN_FADE_MS",
    "SPRING_DAMPING_RATIO",
    "SPRING_MASS",
    "SPRING_STIFFNESS",
    "AxisSpring",
    "Fadable",
    "FadeIn",
    "FadesIn",
    "SizeReporter",
    "animation_speed",
    "duration_ms",
    "enabled",
    "point",
    "rect",
    "set_animation_speed",
    "spring_params",
    "translate",
]
