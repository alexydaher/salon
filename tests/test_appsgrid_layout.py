# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry policy for the All applications grid."""

from __future__ import annotations

import pytest

from salon.core import tokens
from salon.ui.appsgrid_geometry import column_count, grid_metrics
from salon.ui.scale import Scale


def test_apps_grid_uses_the_shared_tile_scale() -> None:
    scale = Scale(1080)
    full = grid_metrics(scale, 1.0)
    compact = grid_metrics(scale, 0.5)

    assert full.width == tokens.tile_size("wide").width_du * 1.35
    assert compact.width == tokens.tile_size("wide").width_du * 0.725
    assert compact.title_size >= 22.0
    assert column_count(1920, scale.safe_margin, compact) > column_count(
        1920, scale.safe_margin, full
    )


def test_apps_grid_cards_are_large_wide_information_cards() -> None:
    wide = tokens.tile_size("wide")
    metrics = grid_metrics(Scale(1080), 1.0)

    assert (metrics.width, metrics.height) == pytest.approx(
        (wide.width_du * 1.35, wide.height_du * 1.35)
    )
    assert metrics.width > metrics.height
