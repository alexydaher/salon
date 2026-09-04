# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation state shared by search UI components."""

from enum import Enum, auto

# What the grid uses before the results pane has been measured, and the
# most it will ever use. Three is what the design asks for; it is no longer
# what the code assumes it got.
MAX_RESULT_COLUMNS = 3


class Pane(Enum):
    KEYBOARD = auto()
    RESULTS = auto()


def result_columns(
    viewport_width: float, step: float, gap: float, *, maximum: int = MAX_RESULT_COLUMNS
) -> int:
    """How many result cards actually fit beside the keyboard.

    This used to be the constant 3, with a comment asserting that "the
    three columns already fill the pane's width". They do not: the keyboard
    takes its own natural width first, and what is left is not a function
    of anything the results grid knows. Measured at 1280×720 — a plain 16:9
    window, and every proportion here is fixed against the viewport's
    height, so the same shortfall exists at 1080p and at 4K — the pane was
    520px while three columns wanted 1065px. The second column was cut in
    half by the window edge, the third was entirely outside it, and because
    the *content* was still sized for three, the focus model moved the
    cursor onto cards nobody could see.

    `step` is one card plus one gap; `gap` is added back because the last
    column needs no trailing gap. Same rule as
    `appsgrid_geometry.column_count`, which had it right.
    """
    if step <= 0:
        return 1
    fits = int((max(0.0, viewport_width) + gap) // step)
    return max(1, min(maximum, fits))
