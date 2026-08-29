# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry policy for the All applications grid."""

from __future__ import annotations

from salon.ui.appsgrid_geometry import column_count, grid_metrics
from salon.ui.scale import Scale


def test_apps_grid_uses_the_shared_tile_scale() -> None:
    scale = Scale(1080)
    full = grid_metrics(scale, 1.0)
    compact = grid_metrics(scale, 0.5)

    assert full.width == 220.0
    assert compact.width == 110.0
    assert compact.title_size >= 22.0
    assert column_count(1920, scale.safe_margin, compact) > column_count(
        1920, scale.safe_margin, full
    )
