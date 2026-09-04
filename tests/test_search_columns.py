# SPDX-License-Identifier: GPL-3.0-or-later
"""How many result cards fit beside the keyboard. See DECISIONS 2026-09-04.

The old code asserted three, in a comment claiming "the three columns
already fill the pane's width". Nothing measured it, and the assertion was
about a pane whose width is whatever the keyboard leaves over.
"""

from __future__ import annotations

from salon.ui.search_models import MAX_RESULT_COLUMNS, result_columns

# One card plus one gap, and the gap on its own. Real values from
# `metrics_for` at the design size.
STEP = 338.0
GAP = 18.0


def test_the_design_width_holds_the_design_column_count() -> None:
    assert result_columns(3 * STEP - GAP, STEP, GAP) == 3


def test_a_pane_one_gap_short_of_three_still_holds_three() -> None:
    """The last column needs no trailing gap; forgetting that loses a
    column whenever the remainder is smaller than one."""
    assert result_columns(3 * STEP - GAP - 1, STEP, GAP) == 2
    assert result_columns(3 * STEP - GAP, STEP, GAP) == 3


def test_a_narrow_pane_drops_columns_instead_of_drawing_off_screen() -> None:
    """Measured at 1280x720: the pane was 520px and three columns wanted
    1065. The second was cut in half by the window edge and the third was
    entirely outside it — and the focus model still moved the cursor onto
    cards nobody could see."""
    assert result_columns(520.0, STEP, GAP) == 1


def test_it_never_exceeds_the_design_count() -> None:
    assert result_columns(10_000.0, STEP, GAP) == MAX_RESULT_COLUMNS


def test_it_never_reports_fewer_than_one() -> None:
    for width in (0.0, -50.0, 3.0):
        assert result_columns(width, STEP, GAP) == 1


def test_a_degenerate_step_does_not_divide_by_zero() -> None:
    assert result_columns(900.0, 0.0, GAP) == 1
