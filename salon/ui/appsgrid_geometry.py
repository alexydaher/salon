# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure sizing policy for the All applications grid."""

from __future__ import annotations

from salon.ui.scale import Scale
from salon.ui.tile_geometry import TileMetrics, metrics_for


def grid_metrics(scale: Scale, tile_scale: float) -> TileMetrics:
    """Wide cards, the same 16:9 shape the home screen uses.

    Square was chosen when the grid was thought of as an application
    launcher and the card as a big icon. But it is the same `TileWidget`
    drawing the same generated artwork, one screen away from the home rows,
    and the shape was the only thing making the two read as different
    surfaces. A wide card is also the better one for a name: it is the axis
    a title runs along, so fewer of them truncate at the same card area.
    """
    # All-app cards carry icon, title and subtitle on one horizontal axis.
    # They therefore use a larger presentation scale than the compact Home
    # tiles while following the same preference proportionally.
    return metrics_for(scale, "wide", size_scale=min(1.35, tile_scale * 1.45))


def horizontal_origin(safe_margin: float, metrics: TileMetrics) -> float:
    return max(0.0, safe_margin - metrics.bleed)


def column_count(viewport_width: int, safe_margin: float, metrics: TileMetrics) -> int:
    if viewport_width <= 0:
        return 1
    left = horizontal_origin(safe_margin, metrics)
    usable = max(1.0, viewport_width - left - metrics.bleed - safe_margin)
    # +gap because the last column needs no trailing gap; without it the
    # grid loses a column whenever the remainder is smaller than one.
    return max(1, int((usable + metrics.gap) // metrics.step))
