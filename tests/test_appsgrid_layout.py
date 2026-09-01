# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry policy for the All applications grid."""

from __future__ import annotations

import pytest

from salon.core.focus import FocusModel
from salon.input.actions import Action
from salon.ui.appsgrid_geometry import (
    column_count,
    grid_metrics,
    grouped_rows,
    linear_neighbor,
)
from salon.ui.scale import Scale


def test_apps_grid_uses_the_shared_tile_scale() -> None:
    scale = Scale(1080)
    full = grid_metrics(scale, 0.55)
    compact = grid_metrics(scale, 0.5)

    assert (full.width, full.height) == pytest.approx((308.0, 138.0))
    assert compact.width == pytest.approx(308.0 * 0.5 / 0.55)
    assert column_count(1920, scale.safe_margin, compact) > column_count(
        1920, scale.safe_margin, full
    )


def test_apps_grid_cards_are_large_wide_information_cards() -> None:
    metrics = grid_metrics(Scale(1080), 0.55)

    assert (metrics.width, metrics.height) == pytest.approx((308.0, 138.0))
    assert metrics.width > metrics.height


def test_apps_grid_navigation_rows_match_the_rendered_letter_groups() -> None:
    rows = grouped_rows(9, 3, [0, 4])

    assert rows == [[0, 1, 2], [3], [4, 5, 6], [7, 8]]


def test_horizontal_navigation_wraps_to_the_next_and_previous_rows() -> None:
    rows = grouped_rows(9, 3, [0, 4])
    positions = {
        index: (row, col)
        for row, indices in enumerate(rows)
        for col, index in enumerate(indices)
    }

    assert positions[linear_neighbor(2, 9, 1)] == (1, 0)
    assert positions[linear_neighbor(3, 9, 1)] == (2, 0)
    assert positions[linear_neighbor(4, 9, -1)] == (1, 0)
    assert linear_neighbor(0, 9, -1) is None
    assert linear_neighbor(8, 9, 1) is None


def test_vertical_navigation_moves_between_visual_rows_in_the_same_column() -> None:
    rows = grouped_rows(9, 3, [0, 4])
    focus = FocusModel([len(row) for row in rows], start=(0, 2))

    focus.handle(Action.DOWN)
    assert focus.position == (1, 0)
    focus.handle(Action.DOWN)
    assert focus.position == (2, 2)
